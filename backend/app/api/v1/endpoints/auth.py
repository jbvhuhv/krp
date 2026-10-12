import random
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
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

        code = f"{random.randint(0, 999999):06d}"
        code_key = f"sms:code:{phone}"
        await redis_client.setex(code_key, settings.SMS_CODE_TTL, code)
        await redis_client.setex(rate_key, settings.SMS_RATE_LIMIT_INTERVAL, "1")
        await redis_client.incr(daily_key)
        await redis_client.expire(daily_key, 86400)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[SMS] 缓存服务不可用: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务暂时不可用，请稍后重试",
        ) from None

    if settings.DEBUG:
        logger.info("[SMS] phone=%s code=%s", phone, code)
    else:
        logger.info("[SMS] phone=%s code=%s", phone, "******")
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

    is_valid = False
    dev_master_code = (
        settings.SMS_DEV_MASTER_CODE
        if settings.DEBUG and settings.ALLOW_DEV_LOGIN
        else ""
    )
    if dev_master_code and code == dev_master_code:
        is_valid = True
    else:
        code_key = f"sms:code:{phone}"
        try:
            stored_code = await redis_client.get(code_key)
            if stored_code and stored_code == code:
                is_valid = True
                await redis_client.delete(code_key)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="验证码错误或已过期",
            ) from None

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码错误或已过期",
        )


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
