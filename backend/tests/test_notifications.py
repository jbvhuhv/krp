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


class TestCommunityNotificationActor:
    """互动通知必须能看出「是谁」——原来的「有人」让作者无从回应。"""

    async def _seed(self, test_db):
        from app.models.community import CommunityPost
        from app.models.user import User

        test_db.add_all(
            [
                User(id="u-author", phone="13800000001", nickname="作者同学"),
                User(id="u-actor", phone="13800000002", nickname="小明"),
            ]
        )
        post = CommunityPost(
            id="p-1",
            user_id="u-author",
            title="数据结构 · 二叉树",
            description="",
            graph_snapshot={"nodes": [], "edges": []},
        )
        test_db.add(post)
        await test_db.commit()
        return post

    async def test_title_carries_actor_nickname(self, test_db):
        from sqlalchemy import select

        from app.api.v1.endpoints.community import notify_post_author
        from app.models.notification import Notification

        post = await self._seed(test_db)
        await notify_post_author(
            test_db, post, "u-actor", "like", "赞了你的知识图谱", "赞了你的知识图谱《x》"
        )

        rows = (await test_db.execute(select(Notification))).scalars().all()
        assert len(rows) == 1
        assert rows[0].title == "小明 赞了你的知识图谱"
        assert rows[0].target_id == "p-1"

    async def test_falls_back_to_masked_phone_without_nickname(self, test_db):
        from sqlalchemy import select

        from app.api.v1.endpoints.community import notify_post_author
        from app.models.notification import Notification
        from app.models.user import User

        post = await self._seed(test_db)
        test_db.add(User(id="u-anon", phone="13900001234", nickname=None))
        await test_db.commit()

        await notify_post_author(
            test_db, post, "u-anon", "comment", "评论了你的知识图谱", "评论了《x》"
        )

        rows = (await test_db.execute(select(Notification))).scalars().all()
        assert rows[-1].title.startswith("139****1234 ")

    async def test_self_action_creates_nothing(self, test_db):
        from sqlalchemy import select

        from app.api.v1.endpoints.community import notify_post_author
        from app.models.notification import Notification

        post = await self._seed(test_db)
        await notify_post_author(
            test_db, post, "u-author", "like", "赞了你的知识图谱", "赞了《x》"
        )

        rows = (await test_db.execute(select(Notification))).scalars().all()
        assert rows == []
