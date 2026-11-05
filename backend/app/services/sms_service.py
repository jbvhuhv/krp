"""短信验证码投递。

之前 /auth/send-code 只把验证码写进 Redis，从不真正发送：演示环境没 Redis 时
返回 503（诚实的失败），一旦补上 Redis 就会变成「提示发送成功、用户永远收不到」
（更糟的假象）。这里把「投递」单独抽出来，让失败可被接口如实翻译成 503。

支持两种通道：
- webhook：生产用。POST JSON 到 SMS_WEBHOOK_URL，由外部网关对接阿里云/腾讯云。
- debug-log：仅 DEBUG 且显式开启时可用，把验证码写进后端日志供本地联调。

两者都不可用时抛 SmsNotConfigured，接口层返回 503 并提示改走演示账号。
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class SmsNotConfigured(RuntimeError):
    """没有任何可用通道——不是「发送失败」，而是「压根没接短信」。"""


class SmsSendFailed(RuntimeError):
    """通道已配置但投递失败（网关超时/5xx），可重试。"""


async def deliver_code(phone: str, code: str) -> str:
    """把验证码投递出去，返回实际使用的通道名；失败抛异常由调用方转 HTTP 状态码。"""
    if settings.SMS_WEBHOOK_URL:
        headers = {"Content-Type": "application/json"}
        if settings.SMS_WEBHOOK_TOKEN:
            headers["Authorization"] = f"Bearer {settings.SMS_WEBHOOK_TOKEN}"
        try:
            async with httpx.AsyncClient(timeout=settings.SMS_WEBHOOK_TIMEOUT) as client:
                resp = await client.post(
                    settings.SMS_WEBHOOK_URL,
                    json={"phone": phone, "code": code, "ttl": settings.SMS_CODE_TTL},
                    headers=headers,
                )
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - 统一翻译成可重试的投递失败
            raise SmsSendFailed(str(exc)) from exc
        return "webhook"

    if settings.DEBUG and settings.SMS_DEBUG_LOG_FALLBACK:
        # 仅本地联调：日志里出现验证码属于预期行为，生产不得开启
        logger.warning("[SMS] DEBUG 通道，验证码=%s phone=%s****%s", code, phone[:3], phone[-4:])
        return "debug-log"

    raise SmsNotConfigured("SMS_WEBHOOK_URL 未配置")
