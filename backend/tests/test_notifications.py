from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.notification_service import NotificationService


@pytest.fixture
async def notification_service(test_db):
    return NotificationService(db=test_db)


class TestNotificationService:
    async def test_create_and_list(self, notification_service):
        await notification_service.create(
            user_id="user-1", title="今日反思提醒", content="有 3 个问题", type="reflection"
        )
        await notification_service.create(
            user_id="user-1", title="系统通知", content="欢迎", type="system"
        )

        data = await notification_service.list_for_user("user-1")

        assert data["total"] == 2
        assert data["unread"] == 2
        assert len(data["items"]) == 2

    async def test_list_isolated_by_user(self, notification_service):
        await notification_service.create(user_id="user-1", title="A")
        await notification_service.create(user_id="user-2", title="B")

        data = await notification_service.list_for_user("user-1")

        assert data["total"] == 1
        assert data["items"][0].title == "A"

    async def test_list_pagination(self, notification_service):
        for i in range(5):
            await notification_service.create(user_id="user-1", title=f"n{i}")

        data = await notification_service.list_for_user("user-1", limit=2, offset=0)

        assert data["total"] == 5
        assert len(data["items"]) == 2

    async def test_mark_read(self, notification_service):
        notification = await notification_service.create(user_id="user-1", title="A")

        updated = await notification_service.mark_read("user-1", notification.id)

        assert updated is not None
        assert updated.is_read is True

        data = await notification_service.list_for_user("user-1")
        assert data["unread"] == 0

    async def test_mark_read_not_found(self, notification_service):
        result = await notification_service.mark_read("user-1", "nonexistent")

        assert result is None

    async def test_mark_read_wrong_user(self, notification_service):
        notification = await notification_service.create(user_id="user-1", title="A")

        result = await notification_service.mark_read("user-2", notification.id)

        assert result is None


class TestNotificationAPI:
    async def test_list_notifications(self, client, mock_notification_service):
        mock_notification_service.list_for_user = AsyncMock(return_value={
            "items": [
                SimpleNamespace(
                    id="n-1",
                    type="reflection",
                    title="今日反思提醒",
                    content="有 3 个问题",
                    is_read=False,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            ],
            "total": 1,
            "unread": 1,
        })

        response = await client.get("/api/v1/notifications")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["unread"] == 1
        assert body["items"][0]["title"] == "今日反思提醒"

    async def test_list_notifications_pagination(self, client, mock_notification_service):
        mock_notification_service.list_for_user = AsyncMock(return_value={
            "items": [], "total": 0, "unread": 0,
        })

        response = await client.get("/api/v1/notifications?limit=5&offset=5")

        assert response.status_code == 200
        call_kwargs = mock_notification_service.list_for_user.call_args.kwargs
        assert call_kwargs["limit"] == 5
        assert call_kwargs["offset"] == 5

    async def test_mark_read_success(self, client, mock_notification_service):
        mock_notification_service.mark_read = AsyncMock(return_value=SimpleNamespace(
            id="n-1",
            type="reflection",
            title="今日反思提醒",
            content="",
            is_read=True,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))

        response = await client.put("/api/v1/notifications/n-1/read")

        assert response.status_code == 200
        assert response.json()["is_read"] is True

    async def test_mark_read_not_found(self, client, mock_notification_service):
        mock_notification_service.mark_read = AsyncMock(return_value=None)

        response = await client.put("/api/v1/notifications/nonexistent/read")

        assert response.status_code == 404
