from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.api.deps import (
    build_notification_service,
    build_reflection_service,
    get_ai_service,
    get_graph_service,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger
from app.models.reflection import ReflectionSchedule
from app.models.user import User

logger = get_logger(__name__)

DEFAULT_JOB_ID = "daily_reflection_default"
SYNC_JOB_ID = "sync_reflection_schedules"

# 调度时区必须与业务日界同一个来源（TIMEZONE_OFFSET_HOURS），
# 否则「20:00 出题」和「今天」两套口径会在换日附近错位。
scheduler = AsyncIOScheduler(
    timezone=timezone(timedelta(hours=settings.TIMEZONE_OFFSET_HOURS))
)


def _parse_time_window(time_window: str) -> tuple[int, int]:
    """'20:00-21:00' → (20, 0)；解析失败回退到全局默认。"""
    try:
        start = (time_window or "").split("-")[0].strip()
        hour, minute = start.split(":")
        return int(hour), int(minute)
    except (ValueError, IndexError, AttributeError):
        return settings.REFLECTION_CRON_HOUR, settings.REFLECTION_CRON_MINUTE


def _frequency_to_day_of_week(frequency: str) -> str | None:
    """daily → None（每天）；weekdays → mon-fri；weekly → sun。"""
    f = (frequency or "daily").strip().lower()
    if f == "weekdays":
        return "mon-fri"
    if f == "weekly":
        return "sun"
    return None


async def _generate_and_notify(user_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        ai_service = get_ai_service()
        graph_service = get_graph_service()
        reflection_service = build_reflection_service(db, ai_service, graph_service)
        notification_service = build_notification_service(db)

        try:
            # 先看今天有没有题：已经有题就不再重复出题、也不再重复推送提醒。
            # 生成走 ensure_today_questions（服务层加锁），否则定时任务和用户手动
            # 点「开始反思」并发时会各生成一套题，同一天同一知识点被问两遍。
            if await reflection_service.get_today_questions(user_id):
                return False
            questions = await reflection_service.ensure_today_questions(
                user_id, max_questions=settings.REFLECTION_DAILY_LIMIT
            )
        except Exception:
            logger.exception("定时反思问题生成失败 user_id=%s", user_id)
            return False

        if not questions:
            return False

        try:
            await notification_service.create(
                user_id=user_id,
                title="今日反思提醒",
                content=f"已为你生成 {len(questions)} 个反思问题，快去回顾一下吧。",
                type="reflection",
                target_type="reflection",
            )
            return True
        except Exception:
            logger.exception("反思提醒推送失败 user_id=%s", user_id)
            return False


async def run_default_reflection_job() -> dict:
    """对没有自定义 schedule 的用户，在全局默认时间触发。"""
    notified = 0
    async with AsyncSessionLocal() as db:
        users_result = await db.execute(select(User))
        all_users = list(users_result.scalars().all())
        sched_result = await db.execute(select(ReflectionSchedule.user_id))
        scheduled_user_ids = {row[0] for row in sched_result.all()}

    for user in all_users:
        if user.id in scheduled_user_ids:
            continue
        if await _generate_and_notify(user.id):
            notified += 1

    logger.info("默认反思任务完成 notified=%d", notified)
    return {"notified": notified}


async def run_user_reflection_job(user_id: str) -> None:
    """按用户自定义 schedule 触发的独立 job。"""
    logger.info("用户反思任务触发 user_id=%s", user_id)
    await _generate_and_notify(user_id)


async def sync_user_schedule_jobs() -> None:
    """读 ReflectionSchedule 表，为每个有设置的用户注册/更新独立 cron job；移除已删除的。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReflectionSchedule))
        schedules = list(result.scalars().all())

    active_user_ids = set()
    for sched in schedules:
        active_user_ids.add(sched.user_id)
        job_id = f"reflection_user_{sched.user_id}"
        hour, minute = _parse_time_window(sched.time_window)
        day_of_week = _frequency_to_day_of_week(sched.frequency)
        trigger_kwargs = {"hour": hour, "minute": minute}
        if day_of_week:
            trigger_kwargs["day_of_week"] = day_of_week
        scheduler.add_job(
            run_user_reflection_job,
            trigger=CronTrigger(**trigger_kwargs),
            id=job_id,
            args=[sched.user_id],
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )

    for job in scheduler.get_jobs():
        if job.id.startswith("reflection_user_"):
            uid = job.id[len("reflection_user_"):]
            if uid not in active_user_ids:
                scheduler.remove_job(job.id)
                logger.info("移除已删除的用户反思调度 user_id=%s", uid)

    logger.info("用户反思调度同步完成 active=%d", len(active_user_ids))


def setup_scheduler() -> AsyncIOScheduler:
    scheduler.add_job(
        run_default_reflection_job,
        trigger=CronTrigger(
            hour=settings.REFLECTION_CRON_HOUR,
            minute=settings.REFLECTION_CRON_MINUTE,
        ),
        id=DEFAULT_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        sync_user_schedule_jobs,
        trigger=CronTrigger(minute="*/30"),
        id=SYNC_JOB_ID,
        replace_existing=True,
        # 启动即同步一次：否则用户改完设置要等到下一个整点/半点才生效
        next_run_time=datetime.now(),
        misfire_grace_time=600,
        coalesce=True,
        max_instances=1,
    )
    if not scheduler.running:
        scheduler.start()
        logger.info(
            "反思调度已启动：默认 %02d:%02d + 每 30 分钟同步用户自定义时段",
            settings.REFLECTION_CRON_HOUR,
            settings.REFLECTION_CRON_MINUTE,
        )
    return scheduler


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("反思定时调度已停止")
