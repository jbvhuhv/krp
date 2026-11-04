from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.avatar import ChatMessage
from app.models.note import Note
from app.models.reflection import ReflectionRecord
from app.services.avatar_service import BLOCK_MESSAGE, AvatarService


async def _aiter(items):
    for item in items:
        yield item


@pytest.fixture
def mock_ai_service():
    service = AsyncMock()
    service.embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
    service.avatar_chat_stream = MagicMock(
        side_effect=lambda **kwargs: _aiter(["F=", "ma", "，力等于质量乘以加速度"])
    )
    service.avatar_smalltalk_stream = MagicMock(
        side_effect=lambda **kwargs: _aiter(["你好呀，", "我是你的知识分身"])
    )
    return service


@pytest.fixture
def mock_graph_service():
    service = AsyncMock()
    service.get_subject_distribution = AsyncMock(return_value={"物理": 3, "数学": 2})
    service.get_mastery_overview = AsyncMock(return_value={
        "total": 5, "avg_mastery": 72.5, "weak": 1, "basic": 2, "proficient": 2,
    })
    service.ensure_vector_index = AsyncMock(return_value=None)
    service.get_nodes_without_embedding = AsyncMock(return_value=[])
    service.set_node_embedding = AsyncMock(return_value=None)
    service.vector_search = AsyncMock(return_value=[])
    service.keyword_search = AsyncMock(return_value=[])
    return service


@pytest.fixture
async def avatar_service(test_db, mock_ai_service, mock_graph_service):
    return AvatarService(
        db=test_db,
        ai_service=mock_ai_service,
        graph_service=mock_graph_service,
    )


class TestGenerateProfile:
    async def test_generate_profile_basic(
        self, avatar_service, test_db
    ):
        record = ReflectionRecord(
            user_id="user-1",
            question="问题",
            answer="回答",
            mastery_score=80.0,
            concept_accuracy=90.0,
            logic_completeness=75.0,
            example_reasonableness=60.0,
        )
        test_db.add(record)
        await test_db.commit()

        profile = await avatar_service.generate_profile("user-1")

        assert profile["domain_distribution"] == {"物理": 3, "数学": 2}
        assert profile["mastery_overview"]["total"] == 5
        assert profile["reflection_style"]["answered"] == 1
        assert profile["reflection_style"]["strongest_dimension"] == "概念准确性"
        assert profile["reflection_style"]["weakest_dimension"] == "举例合理性"
        assert "知识点" in profile["summary"]
        assert isinstance(profile["generated_at"], str)

    async def test_generate_profile_no_reflections(self, avatar_service):
        profile = await avatar_service.generate_profile("user-1")

        assert profile["reflection_style"]["total_reflections"] == 0
        assert profile["reflection_style"]["completion_rate"] == 0.0
        assert profile["reflection_style"]["avg_score"] == 0.0


class TestPublishUnpublish:
    async def test_publish_creates_online_avatar(
        self, avatar_service, mock_graph_service
    ):
        avatar = await avatar_service.publish("user-1")

        assert avatar.status == "online"
        assert avatar.share_token
        assert avatar.profile is not None
        # 分享链接应指向访客可用的聊天页，而不是会重定向的 avatar 页
        assert avatar_service.build_share_url(avatar).endswith(f"/chat/{avatar.id}")
        mock_graph_service.ensure_vector_index.assert_not_called()
        mock_graph_service.get_nodes_without_embedding.assert_called_once()

    async def test_publish_with_config(self, avatar_service):
        avatar = await avatar_service.publish("user-1", config={
            "tone": "lively",
            "welcome_message": "你好呀",
            "knowledge_scope": ["物理"],
        })

        assert avatar.tone == "lively"
        assert avatar.welcome_message == "你好呀"
        assert avatar.knowledge_scope == ["物理"]

    async def test_unpublish_sets_offline(self, avatar_service):
        await avatar_service.publish("user-1")

        avatar = await avatar_service.unpublish("user-1")

        assert avatar.status == "offline"

    async def test_backfill_embeddings(
        self, avatar_service, mock_graph_service, mock_ai_service
    ):
        mock_graph_service.get_nodes_without_embedding = AsyncMock(return_value=[
            {"id": "n1", "name": "牛顿第二定律", "summary": "F=ma"},
            {"id": "n2", "name": "动量守恒", "summary": "总动量不变"},
        ])

        await avatar_service.publish("user-1")

        assert mock_graph_service.set_node_embedding.call_count == 2
        assert mock_ai_service.embed.call_count == 2


class TestRAGSearch:
    async def test_rag_search_returns_hits(
        self, avatar_service, mock_graph_service
    ):
        mock_graph_service.vector_search = AsyncMock(return_value=[
            {"node": {"id": "n1", "name": "牛顿第二定律", "summary": "F=ma"}, "score": 0.9},
        ])

        hits = await avatar_service.rag_search("user-1", "什么是牛顿第二定律")

        assert len(hits) == 1
        assert hits[0]["score"] == 0.9

    async def test_rag_search_without_embedding_client(
        self, avatar_service, mock_ai_service
    ):
        mock_ai_service.embedding = None

        hits = await avatar_service.rag_search("user-1", "问题")

        assert hits == []

    async def test_rag_search_embedding_failure_returns_empty(
        self, avatar_service, mock_ai_service
    ):
        mock_ai_service.embed = AsyncMock(side_effect=Exception("embed down"))

        hits = await avatar_service.rag_search("user-1", "问题")

        assert hits == []


class TestStreamAnswerAntiHallucination:
    async def test_blocked_when_below_threshold(
        self, avatar_service, mock_graph_service, mock_ai_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        avatar.status = "online"
        await test_db.commit()
        mock_graph_service.vector_search = AsyncMock(return_value=[
            {"node": {"id": "n1", "name": "无关知识", "summary": "x"}, "score": 0.4},
        ])

        events = []
        async for event in avatar_service.stream_answer(avatar, "量子纠缠是什么"):
            events.append(event)

        assert len(events) == 1
        assert events[0]["type"] == "blocked"
        assert events[0]["message"] == BLOCK_MESSAGE
        assert events[0]["sources"] == []
        mock_ai_service.avatar_chat_stream.assert_not_called()

    async def test_blocked_persists_messages(
        self, avatar_service, mock_graph_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        mock_graph_service.vector_search = AsyncMock(return_value=[])

        async for _ in avatar_service.stream_answer(avatar, "超纲问题", visitor_id="v1"):
            pass

        from sqlalchemy import func, select
        count = await test_db.scalar(
            select(func.count(ChatMessage.id)).where(ChatMessage.avatar_id == avatar.id)
        )
        assert count == 2

    async def test_stream_answer_success_with_sources(
        self, avatar_service, mock_graph_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        note = Note(
            id="note-1",
            user_id="user-1",
            title="力学笔记",
            format="txt",
            file_path="/x",
            content="内容",
        )
        test_db.add(note)
        await test_db.commit()

        mock_graph_service.vector_search = AsyncMock(return_value=[
            {
                "node": {
                    "id": "n1",
                    "name": "牛顿第二定律",
                    "summary": "F=ma",
                    "subject": "物理",
                    "mastery": 70.0,
                    "source_note_id": "note-1",
                },
                "score": 0.92,
            },
        ])

        events = []
        async for event in avatar_service.stream_answer(avatar, "解释牛顿第二定律"):
            events.append(event)

        types = [e["type"] for e in events]
        assert types[0] == "sources"
        assert "chunk" in types
        assert types[-1] == "done"
        assert events[0]["sources"][0]["note_title"] == "力学笔记"
        assert events[-1]["answer"] == "F=ma，力等于质量乘以加速度"

    async def test_stream_answer_falls_back_to_keyword_search(
        self, avatar_service, mock_graph_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        mock_graph_service.vector_search = AsyncMock(return_value=[])
        mock_graph_service.keyword_search = AsyncMock(return_value=[
            {
                "node": {
                    "id": "n1",
                    "name": "牛顿第二定律",
                    "summary": "F=ma",
                    "subject": "物理",
                    "mastery": 70.0,
                },
                "score": 0.8,
            },
        ])

        events = []
        async for event in avatar_service.stream_answer(avatar, "解释牛顿第二定律"):
            events.append(event)

        types = [e["type"] for e in events]
        assert types[0] == "sources"
        assert types[-1] == "done"
        mock_graph_service.keyword_search.assert_called_once()

    async def test_smalltalk_bypasses_rag(
        self, avatar_service, mock_graph_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()

        events = []
        async for event in avatar_service.stream_answer(avatar, "在干嘛"):
            events.append(event)

        types = [e["type"] for e in events]
        assert "chunk" in types
        assert types[-1] == "done"
        mock_graph_service.vector_search.assert_not_called()
        mock_graph_service.keyword_search.assert_not_called()


class TestGetStats:
    async def test_get_stats_counts(
        self, avatar_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        test_db.add_all([
            ChatMessage(avatar_id=avatar.id, visitor_id="v1", role="user", content="问题A"),
            ChatMessage(avatar_id=avatar.id, visitor_id="v1", role="assistant", content="回答A"),
            ChatMessage(avatar_id=avatar.id, visitor_id="v2", role="user", content="问题B"),
            ChatMessage(avatar_id=avatar.id, visitor_id="v2", role="user", content="问题A"),
        ])
        await test_db.commit()

        stats = await avatar_service.get_stats("user-1", avatar.id)

        assert stats["total_messages"] == 4
        assert stats["total_conversations"] == 2
        assert stats["today_conversations"] == 2
        assert stats["total_conversations"] >= stats["today_conversations"] > 0
        assert stats["top_questions"][0]["question"] == "问题A"
        assert stats["top_questions"][0]["count"] == 2

    async def test_get_stats_anonymous_visitors_collapsed(
        self, avatar_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        test_db.add_all([
            ChatMessage(avatar_id=avatar.id, visitor_id=None, role="user", content="Q1"),
            ChatMessage(avatar_id=avatar.id, visitor_id=None, role="user", content="Q2"),
        ])
        await test_db.commit()

        stats = await avatar_service.get_stats("user-1", avatar.id)

        assert stats["total_conversations"] == 1
        assert stats["today_conversations"] == 1
        assert stats["total_conversations"] >= stats["today_conversations"] > 0

    async def test_get_stats_not_owner(self, avatar_service, test_db):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()

        stats = await avatar_service.get_stats("other-user", avatar.id)

        assert stats is None


class TestConversations:
    async def test_get_conversations_groups_by_visitor(
        self, avatar_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        base = datetime(2026, 1, 1, 12, 0, 0)
        test_db.add_all([
            ChatMessage(avatar_id=avatar.id, visitor_id="v1", role="user", content="问题A", created_at=base),
            ChatMessage(avatar_id=avatar.id, visitor_id="v1", role="assistant", content="回答A", created_at=base + timedelta(seconds=1)),
            ChatMessage(avatar_id=avatar.id, visitor_id="v1", role="user", content="问题A2", created_at=base + timedelta(seconds=2)),
            ChatMessage(avatar_id=avatar.id, visitor_id="v2", role="user", content="问题B", created_at=base + timedelta(seconds=3)),
        ])
        await test_db.commit()

        conversations = await avatar_service.get_conversations("user-1", avatar.id)

        assert conversations is not None
        assert len(conversations) == 2
        by_visitor = {c["visitor_id"]: c for c in conversations}
        assert by_visitor["v1"]["message_count"] == 3
        assert by_visitor["v1"]["question_count"] == 2
        assert by_visitor["v1"]["last_question"] == "问题A2"
        assert by_visitor["v2"]["message_count"] == 1
        assert by_visitor["v1"]["display_name"].startswith("访客")

    async def test_get_conversations_anonymous_collapsed(
        self, avatar_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        test_db.add_all([
            ChatMessage(avatar_id=avatar.id, visitor_id=None, role="user", content="Q1"),
            ChatMessage(avatar_id=avatar.id, visitor_id=None, role="assistant", content="A1"),
        ])
        await test_db.commit()

        conversations = await avatar_service.get_conversations("user-1", avatar.id)

        assert len(conversations) == 1
        assert conversations[0]["visitor_id"] == "anonymous"
        assert conversations[0]["display_name"] == "匿名访客"
        assert conversations[0]["message_count"] == 2

    async def test_get_conversations_not_owner(self, avatar_service, test_db):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()

        assert await avatar_service.get_conversations("other-user", avatar.id) is None

    async def test_get_conversation_returns_messages_in_order(
        self, avatar_service, test_db
    ):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        base = datetime(2026, 1, 1, 12, 0, 0)
        test_db.add_all([
            ChatMessage(avatar_id=avatar.id, visitor_id="v1", role="user", content="Q", created_at=base),
            ChatMessage(avatar_id=avatar.id, visitor_id="v1", role="assistant", content="A", created_at=base + timedelta(seconds=1)),
            ChatMessage(avatar_id=avatar.id, visitor_id="v2", role="user", content="OTHER", created_at=base + timedelta(seconds=2)),
        ])
        await test_db.commit()

        detail = await avatar_service.get_conversation("user-1", avatar.id, "v1")

        assert detail is not None
        assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
        assert [m["content"] for m in detail["messages"]] == ["Q", "A"]

    async def test_get_conversation_anonymous(self, avatar_service, test_db):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()
        test_db.add(
            ChatMessage(avatar_id=avatar.id, visitor_id=None, role="user", content="Q")
        )
        await test_db.commit()

        detail = await avatar_service.get_conversation("user-1", avatar.id, "anonymous")

        assert detail is not None
        assert detail["display_name"] == "匿名访客"
        assert len(detail["messages"]) == 1

    async def test_get_conversation_not_owner(self, avatar_service, test_db):
        avatar = await avatar_service.get_or_create_avatar("user-1")
        await test_db.commit()

        assert await avatar_service.get_conversation("other-user", avatar.id, "v1") is None


class TestAvatarAPI:
    async def test_publish_returns_share_url(self, client, mock_avatar_service):
        mock_avatar_service.publish = AsyncMock(return_value=SimpleNamespace(
            id="avatar-1", share_token="tok-1", status="online",
        ))

        response = await client.post("/api/v1/avatar/publish", json={
            "tone": "rigorous",
            "welcome_message": "你好",
            "knowledge_scope": ["物理"],
        })

        assert response.status_code == 201
        body = response.json()
        assert body["avatar_id"] == "avatar-1"
        assert body["share_token"] == "tok-1"
        assert body["share_url"] == "http://test/avatar/share-token"
        assert body["status"] == "online"

    async def test_update_config(self, client, mock_avatar_service):
        mock_avatar_service.update_config = AsyncMock(return_value=SimpleNamespace(
            id="avatar-1", status="online", tone="lively",
            welcome_message="嗨", knowledge_scope=["数学"], profile=None,
        ))

        response = await client.put("/api/v1/avatar/config", json={
            "tone": "lively",
            "welcome_message": "嗨",
            "knowledge_scope": ["数学"],
        })

        assert response.status_code == 200
        body = response.json()
        assert body["tone"] == "lively"
        assert body["welcome_message"] == "嗨"

    async def test_unpublish(self, client, mock_avatar_service):
        mock_avatar_service.unpublish = AsyncMock(return_value=SimpleNamespace(
            id="avatar-1", status="offline", tone="rigorous",
            welcome_message="", knowledge_scope=[], profile=None,
        ))

        response = await client.post("/api/v1/avatar/unpublish")

        assert response.status_code == 200
        assert response.json()["status"] == "offline"

    async def test_get_me_not_created(self, client, mock_avatar_service):
        mock_avatar_service.get_avatar_for_user = AsyncMock(return_value=None)

        response = await client.get("/api/v1/avatar/me")

        assert response.status_code == 404

    async def test_get_me_success(self, client, mock_avatar_service):
        mock_avatar_service.get_avatar_for_user = AsyncMock(return_value=SimpleNamespace(
            id="avatar-1", status="online", tone="rigorous",
            welcome_message="", knowledge_scope=[], profile=None,
        ))

        response = await client.get("/api/v1/avatar/me")

        assert response.status_code == 200
        assert response.json()["avatar_id"] == "avatar-1"

    async def test_get_stats_not_found(self, client, mock_avatar_service):
        mock_avatar_service.get_stats = AsyncMock(return_value=None)

        response = await client.get("/api/v1/avatar/avatar-1/stats")

        assert response.status_code == 404

    async def test_get_stats_success(self, client, mock_avatar_service):
        mock_avatar_service.get_stats = AsyncMock(return_value={
            "total_conversations": 2,
            "total_messages": 10,
            "top_questions": [{"question": "Q", "count": 3}],
        })

        response = await client.get("/api/v1/avatar/avatar-1/stats")

        assert response.status_code == 200
        assert response.json()["total_messages"] == 10

    async def test_get_conversations_api_success(self, client, mock_avatar_service):
        mock_avatar_service.get_conversations = AsyncMock(return_value=[
            {"visitor_id": "anonymous", "display_name": "匿名访客",
             "message_count": 2, "question_count": 1, "last_question": "Q"},
        ])

        response = await client.get("/api/v1/avatar/avatar-1/conversations")

        assert response.status_code == 200
        body = response.json()
        assert len(body["conversations"]) == 1
        assert body["conversations"][0]["display_name"] == "匿名访客"

    async def test_get_conversations_api_not_found(self, client, mock_avatar_service):
        mock_avatar_service.get_conversations = AsyncMock(return_value=None)

        response = await client.get("/api/v1/avatar/avatar-1/conversations")

        assert response.status_code == 404

    async def test_get_conversation_api_success(self, client, mock_avatar_service):
        mock_avatar_service.get_conversation = AsyncMock(return_value={
            "visitor_id": "v1", "display_name": "访客 · abcdef",
            "messages": [
                {"role": "user", "content": "Q"},
                {"role": "assistant", "content": "A"},
            ],
        })

        response = await client.get("/api/v1/avatar/avatar-1/conversations/v1")

        assert response.status_code == 200
        assert len(response.json()["messages"]) == 2

    async def test_get_conversation_api_empty(self, client, mock_avatar_service):
        mock_avatar_service.get_conversation = AsyncMock(return_value={
            "visitor_id": "v1", "display_name": "访客 · abcdef", "messages": [],
        })

        response = await client.get("/api/v1/avatar/avatar-1/conversations/v1")

        assert response.status_code == 404

    async def test_get_public_avatar_offline(self, client, mock_avatar_service):
        mock_avatar_service.get_by_avatar_id = AsyncMock(return_value=SimpleNamespace(
            id="avatar-1", status="offline", tone="rigorous",
            welcome_message="", knowledge_scope=[], profile=None,
        ))

        response = await client.get("/api/v1/avatar/avatar-1")

        assert response.status_code == 404

    async def test_get_public_avatar_online(self, client, mock_avatar_service):
        mock_avatar_service.get_by_avatar_id = AsyncMock(return_value=SimpleNamespace(
            id="avatar-1", status="online", tone="lively",
            welcome_message="你好", knowledge_scope=["物理"], profile=None,
        ))

        response = await client.get("/api/v1/avatar/avatar-1")

        assert response.status_code == 200
        assert response.json()["welcome_message"] == "你好"
    async def test_get_public_avatar_hides_profile_internals(
        self, client, mock_avatar_service
    ):
        mock_avatar_service.get_by_avatar_id = AsyncMock(return_value=SimpleNamespace(
            id="avatar-1", status="online", tone="lively",
            welcome_message="你好", knowledge_scope=["物理"],
            profile={
                "domain_distribution": {"物理": 3},
                "summary": "共 5 个知识点",
                "mastery_overview": {"total": 5, "avg_mastery": 72.5},
                "reflection_style": {"answered": 3, "avg_score": 80.0},
                "generated_at": "2026-01-01T00:00:00+00:00",
            },
        ))

        response = await client.get("/api/v1/avatar/avatar-1")

        assert response.status_code == 200
        profile = response.json()["profile"]
        assert profile["domain_distribution"] == {"物理": 3}
        assert profile["summary"] == "共 5 个知识点"
        assert profile["mastery_overview"] == {}
        assert profile["reflection_style"] == {}
