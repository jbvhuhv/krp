from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id, get_notification_service
from app.schemas.notification import NotificationList, NotificationOut
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("", response_model=NotificationList)
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    notification_service: NotificationService = Depends(get_notification_service),
):
    data = await notification_service.list_for_user(
        user_id, limit=limit, offset=offset
    )
    return NotificationList(
        items=[
            NotificationOut.model_validate(item, from_attributes=True)
            for item in data["items"]
        ],
        total=data["total"],
        unread=data["unread"],
    )


@router.put("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: str,
    user_id: str = Depends(get_current_user_id),
    notification_service: NotificationService = Depends(get_notification_service),
):
    notification = await notification_service.mark_read(user_id, notification_id)
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知不存在",
        )
    return NotificationOut.model_validate(notification, from_attributes=True)
