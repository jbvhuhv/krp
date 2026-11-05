"""针对本轮加固新增的回归测试。

覆盖：
1. 抽取/评分走结构化输出（response_format）与 temperature=0；
2. 评分结果里模型把数组写成字符串时能收敛；
3. 已作答的题返回当初的薄弱点/资源，且不重复调用模型；
4. 上传配额；
5. 调度器解析用户时段与频率。
"""

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.models.reflection import ReflectionRecord
from app.services.ai.extraction_ai import ExtractionMixin
from app.services.ai.scoring_ai import ScoringMixin
from app.services.providers.base import json_call_kwargs
from app.services.reflection_service import ReflectionService


class _FakeLLM:
    """记录 kwargs 的假 Provider，用来断言结构化输出参数确实传下去了。"""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[dict] = []

    async def chat(self, prompt: str, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.reply


class _Extractor(ExtractionMixin):
    def __init__(self, llm):
        self.llm = llm


class _Scorer(ScoringMixin):
    def __init__(self, llm):
        self.llm = llm


def test_json_call_kwargs_enables_json_mode():
    kwargs = json_call_kwargs()
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["temperature"] == 0


def test_json_call_kwargs_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_JSON_MODE", False)
    kwargs = json_call_kwargs()
    assert "response_format" not in kwargs
    # 温度仍然要固定：评分必须可复现
    assert kwargs["temperature"] == 0


async def test_extraction_requests_json_mode():
    llm = _FakeLLM('{"nodes": [], "categories": [], "edges": []}')
    await _Extractor(llm).extract_knowledge("随便一段笔记")

    assert llm.calls, "未调用模型"
    assert llm.calls[0]["response_format"] == {"type": "json_object"}
    assert llm.calls[0]["temperature"] == 0


async def test_scoring_requests_json_mode_and_coerces_string_lists():
    llm = _FakeLLM(
        '{"concept_accuracy": "85分", "logic_completeness": 70, '
        '"example_reasonableness": "优", '
        '"weak_points": "1. 加速度理解不到位\\n2. 没有举例", '
        '"suggestion": "复习第三章", "resources": "《大学物理》"}'
    )
    result = await _Scorer(llm).evaluate_answer("牛顿第二定律", "解释一下", "F=ma")

    assert llm.calls[0]["response_format"] == {"type": "json_object"}
    # 字符串形式的数组必须收敛成 list[str]，否则前端 v-for 会逐字渲染
    assert result["weak_points"] == ["1. 加速度理解不到位", "2. 没有举例"]
    assert result["resources"] == ["《大学物理》"]
    assert result["concept_accuracy"] == "85分"  # 由 service 层的 _to_score 兜底


@pytest.fixture
def _service(test_db, mock_graph_service):
    ai_service = AsyncMock()
    return ReflectionService(
        db=test_db, ai_service=ai_service, graph_service=mock_graph_service
    ), ai_service


async def test_answered_question_returns_saved_details_without_calling_llm(_service):
    service, ai_service = _service
    record = ReflectionRecord(
        user_id="user-1",
        question="解释动量守恒",
        answer="系统不受外力时总动量不变",
        mastery_score=72.0,
        concept_accuracy=80.0,
        weak_points='["没有提到适用条件"]',
        resources='["《大学物理》第四章"]',
        feedback="补充适用条件",
    )
    service.db.add(record)
    await service.db.commit()
    await service.db.refresh(record)

    result = await service.evaluate_answer("user-1", record.id, "再答一次")

    assert result["already_answered"] is True
    assert result["weak_points"] == ["没有提到适用条件"]
    assert result["resources"] == ["《大学物理》第四章"]
    # 已作答不再重复调用模型，避免同一道题拿到第二个分数
    ai_service.evaluate_answer.assert_not_awaited()


async def test_weak_points_are_persisted_after_evaluation(_service):
    service, ai_service = _service
    ai_service.evaluate_answer = AsyncMock(
        return_value={
            "concept_accuracy": 80.0,
            "logic_completeness": 70.0,
            "example_reasonableness": 60.0,
            "weak_points": ["漏掉了边界条件"],
            "suggestion": "再看一遍定义",
            "resources": ["教材 P32"],
        }
    )
    record = ReflectionRecord(user_id="user-2", question="解释极限", node_name="极限")
    service.db.add(record)
    await service.db.commit()
    await service.db.refresh(record)

    await service.evaluate_answer("user-2", record.id, "当 x 趋近某值时函数值趋近某值")

    await service.db.refresh(record)
    assert record.weak_points == '["漏掉了边界条件"]'
    assert record.resources == '["教材 P32"]'


async def test_upload_quota_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DAILY_LIMIT", 0)
    response = await client.post(
        "/api/v1/notes/upload",
        files={"file": ("note.md", b"# hello", "text/markdown")},
    )
    assert response.status_code == 429
    assert "最多上传" in response.json()["detail"]


def test_scheduler_parses_user_window_and_frequency():
    from app.scheduler import _frequency_to_day_of_week, _parse_time_window

    assert _parse_time_window("19:30-21:00") == (19, 30)
    assert _parse_time_window("") == (
        settings.REFLECTION_CRON_HOUR,
        settings.REFLECTION_CRON_MINUTE,
    )
    assert _parse_time_window("bad") == (
        settings.REFLECTION_CRON_HOUR,
        settings.REFLECTION_CRON_MINUTE,
    )
    assert _frequency_to_day_of_week("daily") is None
    assert _frequency_to_day_of_week("weekdays") == "mon-fri"
    assert _frequency_to_day_of_week("weekly") == "sun"


# ---------------------------------------------------------------------------
# 第二轮加固：快照上限 / 限流 / 注销
# ---------------------------------------------------------------------------


def test_graph_snapshot_rejects_oversized_nodes():
    """发布内容由客户端构造，必须有上限——否则克隆者会被拖进数千次图库写入。"""
    import pydantic

    from app.schemas.community import GraphSnapshot, GraphSnapshotNode

    nodes = [GraphSnapshotNode(id=str(i), name=f"n{i}") for i in range(2001)]
    with pytest.raises(pydantic.ValidationError):
        GraphSnapshot(nodes=nodes)

    ok = GraphSnapshot(
        nodes=[GraphSnapshotNode(id="1", name="a") for _ in range(2000)]
    )
    assert len(ok.nodes) == 2000


async def test_brainstorm_quota_raises_429(monkeypatch):
    from fastapi import HTTPException

    from app.api.v1.endpoints.brainstorm import _check_brainstorm_quota
    from app.core import rate_limit

    rate_limit.reset_all_in_memory()
    # 直接改模块常量：函数体引用的是模块全局名
    import app.api.v1.endpoints.brainstorm as bm

    monkeypatch.setattr(bm, "BRAINSTORM_RPM", 3)

    for _ in range(3):
        await _check_brainstorm_quota("u-brainstorm")
    with pytest.raises(HTTPException) as exc:
        await _check_brainstorm_quota("u-brainstorm")
    assert exc.value.status_code == 429
    rate_limit.reset_all_in_memory()


async def test_delete_me_removes_all_user_data(client, test_db):
    """注销：关系库与图谱数据一并删除，再次请求 /auth/me 返回 401。"""
    from sqlalchemy import select

    from app.api.deps import get_current_user
    from app.main import app
    from app.models.avatar import Avatar, ChatMessage
    from app.models.note import Note
    from app.models.user import User

    user = User(id="del-user-1", phone="13900001111")
    test_db.add(user)
    test_db.add(Note(id="del-note-1", user_id="del-user-1", title="t", content="c"))
    test_db.add(
        Avatar(id="del-avatar-1", user_id="del-user-1", share_token="del-token-1")
    )
    test_db.add(
        ChatMessage(id="del-msg-1", avatar_id="del-avatar-1", role="user", content="hi")
    )
    await test_db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.delete("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "账号已注销，全部个人数据已删除"

        notes = (
            await test_db.execute(select(Note).where(Note.user_id == "del-user-1"))
        ).scalars().all()
        assert notes == []
        # ChatMessage 只挂 avatar_id，是注销级联最容易漏的一张表
        msgs = (
            await test_db.execute(
                select(ChatMessage).where(ChatMessage.avatar_id == "del-avatar-1")
            )
        ).scalars().all()
        assert msgs == []
        gone = (
            await test_db.execute(select(User).where(User.id == "del-user-1"))
        ).scalar_one_or_none()
        assert gone is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_export_me_returns_json_payload(client, test_db):
    from app.api.deps import get_current_user
    from app.main import app
    from app.models.note import Note
    from app.models.user import User

    user = User(id="exp-user-1", phone="13900002222", nickname="导出测试")
    test_db.add(user)
    test_db.add(
        Note(id="exp-note-1", user_id="exp-user-1", title="导出笔记", content="正文")
    )
    await test_db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.get("/api/v1/auth/me/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["id"] == "exp-user-1"
        assert len(data["notes"]) == 1
        assert data["notes"][0]["title"] == "导出笔记"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_sms_without_channel_is_explicitly_503(client, monkeypatch):
    """没接短信通道时必须如实 503，而不是「发送成功」但用户永远收不到。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "SMS_WEBHOOK_URL", "")
    monkeypatch.setattr(settings, "SMS_DEBUG_LOG_FALLBACK", False)

    resp = await client.post("/api/v1/auth/send-code", json={"phone": "13900003333"})
    assert resp.status_code == 503
    assert "短信通道未接入" in resp.json()["detail"]


async def test_sms_webhook_delivers_code(monkeypatch):
    from app.core.config import settings
    from app.services import sms_service

    sent = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            sent.update({"url": url, "json": json, "headers": headers})
            return _Resp()

    monkeypatch.setattr(settings, "SMS_WEBHOOK_URL", "https://sms.example.com/send")
    monkeypatch.setattr(settings, "SMS_WEBHOOK_TOKEN", "tkn")
    monkeypatch.setattr(sms_service.httpx, "AsyncClient", _Client)

    channel = await sms_service.deliver_code("13900004444", "654321")

    assert channel == "webhook"
    assert sent["url"] == "https://sms.example.com/send"
    assert sent["json"] == {"phone": "13900004444", "code": "654321", "ttl": settings.SMS_CODE_TTL}
    assert sent["headers"]["Authorization"] == "Bearer tkn"


async def test_sms_webhook_failure_is_retryable(monkeypatch):
    from app.core.config import settings
    from app.services import sms_service

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            raise RuntimeError("gateway down")

    monkeypatch.setattr(settings, "SMS_WEBHOOK_URL", "https://sms.example.com/send")
    monkeypatch.setattr(sms_service.httpx, "AsyncClient", _Client)

    with pytest.raises(sms_service.SmsSendFailed):
        await sms_service.deliver_code("13900005555", "111111")


def test_ugc_moderation_blocks_obfuscated_words():
    """零宽字符/分隔符是最常见的绕过手法，初筛要先把它们归一化掉。"""
    from app.core.moderation import find_violation

    assert find_violation("正常讨论牛顿第二定律") is None
    assert find_violation("有人能代 考吗") == "代考"
    assert find_violation("代\u200b考包过") == "代考"
    assert find_violation("出售发票，价格私聊") == "出售发票"


async def test_community_post_rejects_blocked_content(test_db):
    from fastapi import HTTPException

    from app.api.v1.endpoints.community import create_post
    from app.schemas.community import GraphSnapshot, PostCreate

    payload = PostCreate(
        title="兼职信息",
        description="可代考，价格私聊",
        graph_snapshot=GraphSnapshot(nodes=[], edges=[]),
        tags=["兼职"],
        is_public=True,
    )
    with pytest.raises(HTTPException) as exc:
        await create_post(payload, user_id="ugc-user", db=test_db)
    assert exc.value.status_code == 400
    assert "违规" in exc.value.detail


# ---------------------------------------------------------------------------
# 出题弱信号 / 模板兜底 / 掌握度溯源
# ---------------------------------------------------------------------------


def _reflection_service(db, graph, ai):
    return ReflectionService(db=db, ai_service=ai, graph_service=graph)


def _ai_stub(question="解释一下这个概念"):
    class _AI:
        async def generate_question(self, node_name, node_summary=""):
            return question

        async def evaluate_answer(self, **kwargs):
            return {
                "concept_accuracy": 80,
                "logic_completeness": 60,
                "example_reasonableness": 40,
                "suggestion": "补充例子",
                "weak_points": ["缺少反例"],
                "resources": ["教材第 3 章"],
            }

    return _AI()


async def test_generate_questions_prefers_fresh_note_node(
    test_db, mock_graph_service
):
    """刚上传笔记的知识点应排到前面，即使它的掌握度不是最低的。"""
    from datetime import datetime, timezone

    from app.models.note import Note
    from app.models.user import User

    test_db.add(User(id="sig-user", phone="13900007771"))
    test_db.add(
        Note(
            id="fresh-note",
            user_id="sig-user",
            title="刚上传的笔记",
            content="内容",
            upload_time=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    await test_db.commit()

    mock_graph_service.get_nodes_for_review = AsyncMock(
        return_value=[
            {"id": "old", "name": "旧知识点", "mastery": 5, "source_note_id": None},
            {
                "id": "fresh",
                "name": "新知识点",
                "mastery": 55,
                "source_note_id": "fresh-note",
            },
        ]
    )

    service = _reflection_service(test_db, mock_graph_service, _ai_stub())
    records = await service.generate_questions("sig-user")

    assert [r.node_name for r in records][0] == "新知识点"
    assert "最近 3 天上传的笔记" in records[0].reason
    # 弱信号只排序，绝不改掌握度
    mock_graph_service.update_mastery.assert_not_called()


async def test_generate_questions_without_signals_keeps_mastery_order(
    test_db, mock_graph_service
):
    mock_graph_service.get_nodes_for_review = AsyncMock(
        return_value=[
            {"id": "low", "name": "低掌握", "mastery": 5},
            {"id": "high", "name": "高掌握", "mastery": 55},
        ]
    )
    service = _reflection_service(test_db, mock_graph_service, _ai_stub())
    records = await service.generate_questions("no-signal-user")

    assert [r.node_name for r in records] == ["低掌握", "高掌握"]
    assert all(r.generated_by == "ai" for r in records)


async def test_template_question_is_stable_per_node():
    from app.services.reflection_service import template_question

    first = template_question("牛顿第二定律", "F=ma，力与加速度同向")
    second = template_question("牛顿第二定律", "F=ma，力与加速度同向")

    assert first == second
    assert "牛顿第二定律" in first
    assert "F=ma" in first


async def test_evaluate_answer_records_mastery_ledger(test_db, mock_graph_service):
    """评分当下就把改前/改后/权重记账，否则事后无法解释掌握度怎么来的。"""
    from app.models.reflection import ReflectionRecord

    record = ReflectionRecord(
        id="ledger-q1", user_id="ledger-user", question="解释牛顿第二定律",
        node_name="牛顿第二定律", target_node_id="node-x",
    )
    test_db.add(record)
    await test_db.commit()

    mock_graph_service.get_node_detail = AsyncMock(
        return_value={"id": "node-x", "mastery": 40.0, "last_reviewed": None}
    )

    service = _reflection_service(test_db, mock_graph_service, _ai_stub())
    result = await service.evaluate_answer("ledger-user", "ledger-q1", "答案")

    await test_db.refresh(record)
    # 80*0.4 + 60*0.35 + 40*0.25 = 63
    assert result["mastery_score"] == pytest.approx(63.0)
    assert record.mastery_before == pytest.approx(40.0)
    assert record.mastery_after is not None
    assert record.mastery_weight is not None
    assert result["mastery_synced"] is True


async def test_evaluate_answer_survives_readonly_graph(test_db, mock_graph_service):
    """图谱只读（演示模式）时不能丢掉整个评分，但要如实说掌握度没同步。"""
    from app.models.reflection import ReflectionRecord

    test_db.add(
        ReflectionRecord(
            id="ro-q1", user_id="ro-user", question="解释概念",
            node_name="概念", target_node_id="node-ro",
        )
    )
    await test_db.commit()

    from app.core.exceptions import ForbiddenException

    mock_graph_service.get_node_detail = AsyncMock(
        side_effect=ForbiddenException("只读图谱")
    )

    service = _reflection_service(test_db, mock_graph_service, _ai_stub())
    result = await service.evaluate_answer("ro-user", "ro-q1", "答案")

    assert result["mastery_score"] == pytest.approx(63.0)
    assert result["mastery_synced"] is False


async def test_node_mastery_detail_reports_ledger(test_db, mock_graph_service):
    from datetime import datetime, timezone

    from app.models.reflection import ReflectionRecord

    test_db.add(
        ReflectionRecord(
            id="detail-q1", user_id="detail-user", question="问", answer="答",
            node_name="牛顿第二定律", target_node_id="node-d",
            mastery_score=62.0, concept_accuracy=80.0, logic_completeness=60.0,
            example_reasonableness=40.0, mastery_before=40.0, mastery_after=53.2,
            mastery_weight=0.78,
            answered_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    await test_db.commit()
    mock_graph_service.get_node_detail = AsyncMock(
        return_value={"id": "node-d", "name": "牛顿第二定律", "mastery": 53.2}
    )

    service = _reflection_service(test_db, mock_graph_service, _ai_stub())
    data = await service.get_node_mastery_detail("detail-user", "node-d")

    assert data["review_count"] == 1
    assert data["timeline"][0]["mastery_before"] == 40.0
    assert data["timeline"][0]["mastery_after"] == 53.2
    assert data["timeline"][0]["recorded"] is True
    assert data["weights"]["concept"] == 0.4


async def test_node_view_endpoint_records_signal(client, test_db):
    """节点查看埋点要落库，它是反思出题的第三个弱信号。"""
    from sqlalchemy import select

    from app.models.reflection import NodeView

    resp = await client.post("/api/v1/graph/nodes/node-view-1/view")
    assert resp.status_code == 204

    rows = (
        (
            await test_db.execute(
                select(NodeView).where(NodeView.node_id == "node-view-1")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].user_id == "test-user-0001"


async def test_node_mastery_endpoint_returns_ledger(client):
    from app.api.deps import get_reflection_service
    from app.main import app

    service = AsyncMock()
    service.get_node_mastery_detail = AsyncMock(
        return_value={
            "node_id": "node-1",
            "node_name": "牛顿第二定律",
            "mastery": 53.2,
            "last_reviewed": None,
            "review_count": 1,
            "timeline": [
                {
                    "record_id": "r1",
                    "time": "2026-11-05T10:00:00+00:00",
                    "score": 63.0,
                    "concept_accuracy": 80.0,
                    "logic_completeness": 60.0,
                    "example_reasonableness": 40.0,
                    "mastery_before": 40.0,
                    "mastery_after": 53.2,
                    "new_weight": 0.78,
                    "recorded": True,
                }
            ],
            "weights": {
                "concept": 0.4,
                "logic": 0.35,
                "example": 0.25,
                "base_new_weight": 0.6,
                "halflife_days": 14.0,
            },
        }
    )
    app.dependency_overrides[get_reflection_service] = lambda: service

    resp = await client.get("/api/v1/reflection/nodes/node-1/mastery")

    assert resp.status_code == 200
    body = resp.json()
    assert body["review_count"] == 1
    assert body["timeline"][0]["mastery_before"] == 40.0
    assert body["timeline"][0]["recorded"] is True


async def test_node_mastery_endpoint_404_when_unknown(client):
    from app.api.deps import get_reflection_service
    from app.main import app

    service = AsyncMock()
    service.get_node_mastery_detail = AsyncMock(
        return_value={
            "node_id": "nope",
            "node_name": "",
            "mastery": 0.0,
            "last_reviewed": None,
            "review_count": 0,
            "timeline": [],
            "weights": {
                "concept": 0.4,
                "logic": 0.35,
                "example": 0.25,
                "base_new_weight": 0.6,
                "halflife_days": 14.0,
            },
        }
    )
    app.dependency_overrides[get_reflection_service] = lambda: service

    resp = await client.get("/api/v1/reflection/nodes/nope/mastery")
    assert resp.status_code == 404
