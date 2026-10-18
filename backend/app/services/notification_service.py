from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.notification import Notification

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: str,
        title: str,
        content: str = "",
        type: str = "system",
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            title=title,
            content=content,
            type=type,
            target_type=target_type,
            target_id=target_id,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        logger.info("站内信已创建 user_id=%s type=%s title=%s", user_id, type, title)
        return notification

    async def list_for_user(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> dict:
        total = await self.db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id
            )
        )
        unread = await self.db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        result = await self.db.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return {
            "items": list(result.scalars().all()),
            "total": total or 0,
            "unread": unread or 0,
        }

    async def mark_read(
        self, user_id: str, notification_id: str
    ) -> Notification | None:
        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            return None
        notification.is_read = True
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def mark_all_read(self, user_id: str) -> int:
        """把该用户所有未读通知标记为已读，返回受影响条数。

        之前只有单条标记，配合「只显示最新 N 条」会让更早的未读通知永远不可达，
        红点也就永远清不掉。
        """
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        await self.db.commit()
        return int(result.rowcount or 0)
