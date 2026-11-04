import re
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core import rate_limit
from app.core.config import settings
from app.core.database import redis_client
from app.core.logger import get_logger
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import LoginRequest, SendCodeRequest, Token, UserOut, UserUpdate
from app.services import pet_service

router = APIRouter()
logger = get_logger(__name__)

PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


@router.post("/send-code", status_code=status.HTTP_200_OK)
async def send_code(payload: SendCodeRequest):
    phone = payload.phone

    rate_key = f"sms:rate:{phone}"
    daily_key = f"sms:daily:{phone}:{date.today().isoformat()}"

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

        code = f"{secrets.randbelow(1_000_000):06d}"
        code_key = f"sms:code:{phone}"
        await redis_client.setex(code_key, settings.SMS_CODE_TTL, code)
        await redis_client.setex(rate_key, settings.SMS_RATE_LIMIT_INTERVAL, "1")
        await redis_client.incr(daily_key)
        await redis_client.expire(daily_key, 86400)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[SMS] 缓存服务不可用: %s", exc)
        # 演示环境没有 Redis，验证码根本存不下来，用户看到「发送成功」才是更糟的假象。
        # 这里把原因和出路一起说清楚，避免访客在登录框上反复点「获取验证码」。
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="短信验证码服务暂不可用（未配置缓存服务），请使用演示账号登录",
        ) from None

    # 安全：验证码明文绝不写入日志（日志通常被采集/长期保留）。只记录脱敏号码。
    logger.info("[SMS] 验证码已生成并下发 phone=%s****%s", phone[:3], phone[-4:])
    return {"message": "验证码已发送"}


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
