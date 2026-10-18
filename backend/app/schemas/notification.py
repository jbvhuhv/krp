from pydantic import BaseModel

from app.schemas.common import UtcDateTime


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    content: str = ""
    is_read: bool = False
    # 关联对象：前端据此跳转。历史通知为 None。
    target_type: str | None = None
    target_id: str | None = None
    created_at: UtcDateTime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
