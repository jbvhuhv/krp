import re
import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_graph_service
from app.core import rate_limit
from app.core.config import settings
from app.core.database import redis_client
from app.core.logger import get_logger
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import LoginRequest, SendCodeRequest, Token, UserOut, UserUpdate
from app.services import pet_service, sms_service

router = APIRouter()
logger = get_logger(__name__)

PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


@router.post("/send-code", status_code=status.HTTP_200_OK)
async def send_code(payload: SendCodeRequest):
    phone = payload.phone

    rate_key = f"sms:rate:{phone}"
    daily_key = f"sms:daily:{phone}:{date.today().isoformat()}"
    code_key = f"sms:code:{phone}"
    code = f"{secrets.randbelow(1_000_000):06d}"

    # 先确认「有地方投递」，再落库：没接短信通道时不该写验证码、也不该占用频控额度
    if not settings.SMS_WEBHOOK_URL and not (
        settings.DEBUG and settings.SMS_DEBUG_LOG_FALLBACK
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="短信通道未接入，请使用演示账号登录",
        )

    try:
        last_sent = await redis_client.get(rate_key)
        if last_sent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="发送过于频繁，请60秒后重试",
            )

        daily_count = await redis_client.get(daily_key)
        if daily_count and int(daily_count) >= settings.SMS_DAILY_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日发送次数已达上限",
            )

        await redis_client.setex(code_key, settings.SMS_CODE_TTL, code)
        await redis_client.setex(rate_key, settings.SMS_RATE_LIMIT_INTERVAL, "1")
        await redis_client.incr(daily_key)
        await redis_client.expire(daily_key, 86400)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[SMS] 缓存服务不可用: %s", exc)
        # 验证码存不下来时，即便短信发出去也无法校验：宁可明确报错，也不假装成功。
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="短信验证码服务暂不可用（未配置缓存服务），请使用演示账号登录",
        ) from None

    try:
        channel = await sms_service.deliver_code(phone, code)
    except sms_service.SmsNotConfigured:
        await _quiet_delete(code_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="短信通道未接入，请使用演示账号登录",
        ) from None
    except sms_service.SmsSendFailed as exc:
        # 投递失败要把验证码和频控一起回滚，否则用户 60 秒内无法重试
        await _quiet_delete(code_key)
        await _quiet_delete(rate_key)
        logger.warning("[SMS] 网关投递失败 phone=%s****%s err=%s", phone[:3], phone[-4:], exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="验证码发送失败，请稍后重试",
        ) from None

    # 安全：验证码明文绝不写入日志（日志通常被采集/长期保留）。只记录脱敏号码。
    logger.info("[SMS] 验证码已下发 channel=%s phone=%s****%s", channel, phone[:3], phone[-4:])
    return {"message": "验证码已发送"}


async def _quiet_delete(key: str) -> None:
    """回滚缓存失败不应盖住真正的错误。"""
    try:
        await redis_client.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("[SMS] 回滚缓存失败 key=%s", key)


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    phone = payload.phone
    code = payload.code

    if not PHONE_PATTERN.match(phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号格式不正确",
        )

    # 登录失败次数限制：同一手机号在窗口期内失败过多则暂时拒绝，防止 6 位验证码被枚举。
    # 计数统一走 rate_limit：优先 Redis，缓存不可用时自动降级为进程内计数——
    # 原实现是「缓存异常就跳过限流」，等于 Redis 一挂，登录爆破就没有任何约束。
    fail_key = f"login:fail:{phone}"
    if await rate_limit.get(fail_key) >= settings.LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请稍后再试",
        )

    is_valid = False
    dev_master_code = (
        settings.SMS_DEV_MASTER_CODE
        if settings.DEBUG and settings.ALLOW_DEV_LOGIN
        else ""
    )
    # 安全：万能码只对白名单手机号生效。只校验 code 不校验 phone 的话，
    # 任何人拿着公开的万能码 + 对方手机号，就能直接登进对方账号（账号接管）。
    if (
        dev_master_code
        and phone in settings.dev_login_allowlist()
        and secrets.compare_digest(code, dev_master_code)
    ):
        is_valid = True
        logger.warning(
            "[AUTH] 使用开发万能验证码登录 phone=%s****%s", phone[:3], phone[-4:]
        )
    else:
        code_key = f"sms:code:{phone}"
        try:
            stored_code = await redis_client.get(code_key)
        except Exception:  # noqa: BLE001 - 缓存不可用等价于验证码不存在，走失败分支
            stored_code = None
        if stored_code and secrets.compare_digest(stored_code, code):
            is_valid = True
            try:
                await redis_client.delete(code_key)
            except Exception:  # noqa: BLE001 - 删除失败不影响本次登录结果
                pass

    if not is_valid:
        await rate_limit.incr(fail_key, settings.LOGIN_FAILURE_WINDOW_SECONDS)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码错误或已过期",
        )

    # 登录成功：清除失败计数，避免正常用户被历史失败拖累
    await rate_limit.reset(fail_key)


    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(phone=phone)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        # 注册即生成一只独特宠物
        await pet_service.create_pet_for_user(db, user.id)

    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserOut(
        id=current_user.id,
        phone=current_user.phone,
        student_id=current_user.student_id,
        nickname=current_user.nickname,
    )


@router.put("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if "nickname" in payload.model_fields_set:
        current_user.nickname = payload.nickname
        db.add(current_user)
        await db.commit()
        await db.refresh(current_user)
    return UserOut(
        id=current_user.id,
        phone=current_user.phone,
        student_id=current_user.student_id,
        nickname=current_user.nickname,
    )


@router.get("/me/export")
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """数据可携带权（个保法第 45 条）：导出用户本人全部数据的 JSON。"""
    from app.models.avatar import Avatar, ChatMessage
    from app.models.community import CommunityComment, CommunityPost
    from app.models.note import Note
    from app.models.notification import Notification
    from app.models.pet import Pet, PetMessage
    from app.models.reflection import ReflectionRecord, ReflectionSchedule

    uid = current_user.id

    def _jsonable(value):
        """保证导出物是合法 JSON：时间转 ISO 字符串，JSON 列原样保留。"""
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return value

    async def _all(model, condition=None):
        stmt = select(model).where(condition if condition is not None else model.user_id == uid)
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {c.name: _jsonable(getattr(r, c.name)) for c in model.__table__.columns}
            for r in rows
        ]

    posts = await _all(CommunityPost)
    pet = await _all(Pet)
    # ChatMessage 挂的是 avatar_id，没有 user_id，需先按用户的数字人筛选
    avatar_ids = (
        await db.execute(select(Avatar.id).where(Avatar.user_id == uid))
    ).scalars().all()
    avatar_messages = (
        await _all(ChatMessage, ChatMessage.avatar_id.in_(avatar_ids))
        if avatar_ids
        else []
    )
    return {
        "user": {
            "id": current_user.id,
            "phone": current_user.phone,
            "student_id": current_user.student_id,
            "nickname": current_user.nickname,
            "created_at": current_user.created_at.isoformat()
            if current_user.created_at
            else None,
        },
        "notes": await _all(Note),
        "reflection_records": await _all(ReflectionRecord),
        "reflection_schedules": await _all(ReflectionSchedule),
        "pets": pet,
        "pet_messages": await _all(PetMessage),
        "avatars": await _all(Avatar),
        "avatar_messages": avatar_messages,
        "community_posts": posts,
        "community_comments": await _all(CommunityComment),
        "notifications": await _all(Notification),
        "exported_at": date.today().isoformat(),
    }


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_me(
    current_user: User = Depends(get_current_user),
    graph_service=Depends(get_graph_service),
    db: AsyncSession = Depends(get_db),
):
    """注销账号（个保法第 47 条）：删除本人全部数据，图谱与关系库一并清理。

    注意：JWT 无状态无法吊销，注销后令牌在自然过期前仍能通过签名校验，
    但所有查询都会因用户不存在而失败，等同于失效。
    """
    from sqlalchemy import delete as sa_delete

    from app.models.avatar import Avatar, ChatMessage
    from app.models.community import (
        CommunityComment,
        CommunityLike,
        CommunityPost,
        CommunityPostView,
    )
    from app.models.note import Note
    from app.models.notification import Notification
    from app.models.pet import Pet, PetMessage
    from app.models.reflection import ReflectionRecord, ReflectionSchedule

    uid = current_user.id

    # 1) 图谱节点：Neo4j 不可用不阻断注销，关系库照删（留下孤儿节点可由巡检清理）
    graph_deleted = 0
    try:
        graph_deleted = await graph_service.delete_all_nodes(uid)
    except Exception:  # noqa: BLE001
        logger.warning("注销时清理图谱失败 user_id=%s", uid, exc_info=True)

    # 2) 社区：本人帖子的互动数据先删，避免悬挂外键
    post_ids = (
        await db.execute(select(CommunityPost.id).where(CommunityPost.user_id == uid))
    ).scalars().all()
    if post_ids:
        for model in (CommunityLike, CommunityComment, CommunityPostView):
            await db.execute(
                sa_delete(model).where(model.post_id.in_(post_ids))
            )
        await db.execute(
            sa_delete(CommunityPost).where(CommunityPost.user_id == uid)
        )
    for model in (CommunityLike, CommunityComment, CommunityPostView):
        await db.execute(sa_delete(model).where(model.user_id == uid))

    # 3) 数字人对话：ChatMessage 只挂 avatar_id，必须先于 Avatar 删除
    avatar_ids = (
        await db.execute(select(Avatar.id).where(Avatar.user_id == uid))
    ).scalars().all()
    if avatar_ids:
        await db.execute(sa_delete(ChatMessage).where(ChatMessage.avatar_id.in_(avatar_ids)))

    # 4) 其余业务数据
    for model in (
        Avatar,
        PetMessage,
        Pet,
        ReflectionRecord,
        ReflectionSchedule,
        Notification,
        Note,
    ):
        await db.execute(sa_delete(model).where(model.user_id == uid))

    # 5) 用户本体（学号、手机号等个人信息随之删除）
    await db.execute(sa_delete(User).where(User.id == uid))
    await db.commit()
    logger.info(
        "账号已注销 user_id=%s graph_nodes_deleted=%d", uid, graph_deleted
    )
    return {"detail": "账号已注销，全部个人数据已删除", "graph_nodes_deleted": graph_deleted}
