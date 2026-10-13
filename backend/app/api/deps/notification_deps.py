from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db


def build_notification_service(db: AsyncSession):
    from app.services.notification_service import NotificationService

    return NotificationService(db=db)


async def get_notification_service(db: AsyncSession = Depends(get_db)):
    return build_notification_service(db)
