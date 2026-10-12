from pydantic import BaseModel

from app.schemas.common import UtcDateTime


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    content: str = ""
    is_read: bool = False
    created_at: UtcDateTime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
