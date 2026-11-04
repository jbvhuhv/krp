"""验证码 / 登录失败次数的计数器。

为什么需要这一层：
    原实现直接读写 Redis，Redis 不可用时调用点只能 `except: pass` —— 缓存一挂，
    登录失败次数限制就整体消失（日志里只是「失败计数不可用」），6 位验证码等于可无限枚举。
    这里把「计数」收敛成一个接口：优先 Redis（多进程/多实例一致），
    Redis 不可用时退回进程内计数，保证「缓存故障 ≠ 限流失效」。

进程内计数只是兜底闸门，单进程有效、重启清零；多实例部署仍应保证 Redis 可用。
"""

from __future__ import annotations

import time
from typing import Final

from app.core.database import redis_client
from app.core.logger import get_logger

logger = get_logger(__name__)

# key -> (count, expire_at_monotonic)
_MEMORY: dict[str, tuple[int, float]] = {}
# 超过阈值才做一次过期清理，避免每次调用都遍历字典
_PRUNE_THRESHOLD: Final = 512
# 硬上限：异常场景（大量随机手机号刷接口）下防止进程内计数无限膨胀
_MEMORY_MAX: Final = 50_000


def _prune_expired(now: float) -> None:
    for key in [k for k, (_, exp) in _MEMORY.items() if exp <= now]:
        _MEMORY.pop(key, None)


def _memory_incr(key: str, ttl: int) -> int:
    now = time.monotonic()
    if len(_MEMORY) > _PRUNE_THRESHOLD:
        _prune_expired(now)
    if len(_MEMORY) > _MEMORY_MAX:
        # 极端情况：宁可丢弃计数也不拖垮进程（Redis 正常时不会走到这里）
        _MEMORY.clear()
    count, expire_at = _MEMORY.get(key, (0, now + ttl))
    if expire_at <= now:
        count, expire_at = 0, now + ttl
    count += 1
    _MEMORY[key] = (count, expire_at)
    return count


def _memory_get(key: str) -> int:
    item = _MEMORY.get(key)
    if item is None:
        return 0
    count, expire_at = item
    if expire_at <= time.monotonic():
        _MEMORY.pop(key, None)
        return 0
    return count


# 降级告警的节流时间戳：Redis 长期不可用时（例如生产只起 app + neo4j），
# 每次调用都打一条 WARNING 会把日志刷满、掩盖真正的错误，这里最多每分钟一条。
_WARN_AT: float = 0.0


def _warn_degraded(key: str, exc: Exception) -> None:
    global _WARN_AT
    now = time.monotonic()
    if now - _WARN_AT < 60:
        return
    _WARN_AT = now
    logger.warning(
        "[RATE] Redis 不可用，改用进程内计数 key=%s (%s)", key, type(exc).__name__
    )


async def incr(key: str, ttl: int) -> int:
    """计数 +1 并返回当前值；首次写入时设置过期时间。"""
    try:
        value = await redis_client.incr(key)
        if int(value) == 1:
            await redis_client.expire(key, ttl)
        return int(value)
    except Exception as exc:  # noqa: BLE001 - 缓存不可用时降级，不能阻断登录
        _warn_degraded(key, exc)
        return _memory_incr(key, ttl)


async def get(key: str) -> int:
    """读取当前计数；键不存在或已过期返回 0。"""
    try:
        raw = await redis_client.get(key)
        return int(raw) if raw else 0
    except Exception as exc:  # noqa: BLE001 - 同上
        _warn_degraded(key, exc)
        return _memory_get(key)


async def reset(key: str) -> None:
    """清零计数（登录成功后调用）。两侧都清，避免 Redis 恢复后读到旧值。"""
    try:
        await redis_client.delete(key)
    except Exception:  # noqa: BLE001 - 清零失败不影响主流程
        pass
    _MEMORY.pop(key, None)


def reset_all_in_memory() -> None:
    """仅测试使用：清空进程内计数。"""
    _MEMORY.clear()
