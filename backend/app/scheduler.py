from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
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
from app.models.user import User

logger = get_logger(__name__)

JOB_ID = "daily_reflection"

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def run_daily_reflection_job() -> dict:
    users_processed = 0
    notified = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User))
        users = list(result.scalars().all())

        ai_service = get_ai_service()
        graph_service = get_graph_service()
        reflection_service = build_reflection_service(db, ai_service, graph_service)
        notification_service = build_notification_service(db)

        for user in users:
            try:
                questions = await reflection_service.generate_questions(
                    user.id, max_questions=settings.REFLECTION_DAILY_LIMIT
                )
            except Exception:
                logger.exception("定时反思问题生成失败 user_id=%s", user.id)
                continue

            if not questions:
                continue

            users_processed += 1
            try:
                await notification_service.create(
                    user_id=user.id,
                    title="今日反思提醒",
                    content=f"已为你生成 {len(questions)} 个反思问题，快去回顾一下吧。",
                    type="reflection",
                )
                notified += 1
            except Exception:
                logger.exception("反思提醒推送失败 user_id=%s", user.id)

    logger.info("每日反思任务完成 users=%d notified=%d", users_processed, notified)
    return {"users_processed": users_processed, "notified": notified}


def setup_scheduler() -> AsyncIOScheduler:
    scheduler.add_job(
        run_daily_reflection_job,
        trigger=CronTrigger(
            hour=settings.REFLECTION_CRON_HOUR,
            minute=settings.REFLECTION_CRON_MINUTE,
        ),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    if not scheduler.running:
        scheduler.start()
        logger.info(
            "反思定时调度已启动，每日 %02d:%02d",
            settings.REFLECTION_CRON_HOUR,
            settings.REFLECTION_CRON_MINUTE,
        )
    return scheduler


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("反思定时调度已停止")
