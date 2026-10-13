"""笔记抽取任务自愈。

抽取通过 FastAPI ``BackgroundTasks`` 在进程内执行，服务重启会丢掉排队中的任务，
导致笔记永远停在 ``pending`` / ``processing``——前端表现为一直"排队中"转圈，
且在笔记列表里长期堆着无法处理的记录。

启动时把这些滞留记录标记为 ``failed``，并给出可操作的提示（前端会显示失败状态与「重抽」按钮）。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.constants import NOTE_STATUS
from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger
from app.models.note import Note

logger = get_logger(__name__)

# 超过该时长仍处于 pending/processing 视为滞留（正常抽取在 1 分钟内完成）
STALE_AFTER = timedelta(minutes=10)
STALE_MESSAGE = "抽取任务因服务重启而中断，请点击「重抽」重新生成"


def _as_naive_utc(value: datetime) -> datetime:
    """统一成不带时区的 UTC，便于与 SQLite 中存储的朴素时间比较。"""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


async def recover_stale_notes() -> int:
    """把滞留的抽取任务标记为失败，返回处理条数。

    该函数只在启动时调用，任何异常都不得阻断服务启动。
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Note).where(
                    Note.status.in_(
                        [NOTE_STATUS["PENDING"], NOTE_STATUS["PROCESSING"]]
                    )
                )
            )
            cutoff = _as_naive_utc(datetime.now(timezone.utc) - STALE_AFTER)
            stale = [
                note
                for note in result.scalars().all()
                if note.upload_time is None or _as_naive_utc(note.upload_time) < cutoff
            ]
            if not stale:
                return 0
            now = datetime.now(timezone.utc)
            for note in stale:
                note.status = NOTE_STATUS["FAILED"]
                note.error_message = STALE_MESSAGE
                note.processed_time = now
            await session.commit()
        logger.warning(
            "启动自愈：已将 %d 条滞留的抽取任务标记为失败（服务重启导致任务丢失）",
            len(stale),
        )
        return len(stale)
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动自愈失败（不影响服务启动）：%s", exc)
        return 0
