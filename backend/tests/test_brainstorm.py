import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.deps import get_ai_service
from app.api.v1.endpoints.brainstorm import _normalize_node_type, _to_node
from app.main import app

TREE_DATA = {
    "book": {"id": "book-1", "name": "物理知识书"},
    "nodes": [
        {
            "id": "node-1",
            "name": "牛顿第二定律",
            "summary": "F=ma",
            "parent_id": "book-1",
            "node_type": "knowledge",
        },
        {
            "id": "node-2",
            "name": "力学",
            "summary": "",
            "parent_id": "book-1",
            "node_type": "category",
        },
    ],
    "edges": [],
}


@pytest.fixture
def mock_ai_service():
    service = MagicMock()
    service.verify_structure = AsyncMock(
        return_value={"overall": "整体合理", "issues": [], "missing": []}
    )
    service.suggest_hint = AsyncMock(
        return_value={"suggestions": [{"name": "惯性", "reason": "基础概念"}]}
    )
    service.guide_idea = AsyncMock(return_value={"guidance": "先想想受力分析"})
    service.generate_subtree = AsyncMock(
        return_value={"nodes": [{"name": "受力分析", "node_type": "category"}]}
    )
    return service


@pytest.fixture
def ai_override(mock_ai_service):
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    yield mock_ai_service
    app.dependency_overrides.pop(get_ai_service, None)


class TestVerifyEndpoint:
    async def test_verify_success_maps_node_name_to_id(
        self, client, mock_graph_service, mock_ai_service, ai_override
    ):
        mock_graph_service.get_tree = AsyncMock(return_value=TREE_DATA)
        mock_ai_service.verify_structure = AsyncMock(return_value={
            "overall": "结构尚可",
            "issues": [{"node_name": "牛顿第二定律", "status": "misplaced", "reason": "应归入力学"}],
            "missing": [{"name": "惯性", "summary": "物体保持运动状态", "reason": "基础"}],
        })

        response = await client.post(
            "/api/v1/brainstorm/verify", json={"book_id": "book-1"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["overall"] == "结构尚可"
        assert body["issues"][0]["node_id"] == "node-1"
        assert body["issues"][0]["status"] == "misplaced"
        assert body["missing"][0]["name"] == "惯性"

    async def test_verify_book_not_found(self, client, mock_graph_service, ai_override):
        mock_graph_service.get_tree = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/brainstorm/verify", json={"book_id": "missing"}
        )

        assert response.status_code == 404
        assert "书籍" in response.json()["detail"]

    async def test_verify_node_not_found(self, client, mock_graph_service, ai_override):
        mock_graph_service.get_tree = AsyncMock(return_value=TREE_DATA)

        response = await client.post(
            "/api/v1/brainstorm/verify",
            json={"book_id": "book-1", "node_id": "nope"},
        )

        assert response.status_code == 404
        assert "节点" in response.json()["detail"]

    async def test_verify_degraded(self, client, mock_graph_service, mock_ai_service, ai_override):
        mock_graph_service.get_tree = AsyncMock(return_value=TREE_DATA)
        mock_ai_service.verify_structure = AsyncMock(
            return_value={"status": "failed", "message": "AI繁忙，请稍后重试"}
        )

        response = await client.post(
            "/api/v1/brainstorm/verify", json={"book_id": "book-1"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["issues"] == []


class TestSuggestEndpoint:
    async def test_hint_without_idea_returns_suggestions(
        self, client, mock_graph_service, ai_override
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={"id": "node-1", "name": "牛顿第二定律", "summary": "F=ma"}
        )

        response = await client.post(
            "/api/v1/brainstorm/suggest",
            json={"book_id": "book-1", "node_id": "node-1", "mode": "hint"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "hint"
        assert body["suggestions"][0]["name"] == "惯性"

    async def test_hint_with_idea_returns_guidance(
        self, client, mock_graph_service, mock_ai_service, ai_override
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={"id": "node-1", "name": "牛顿第二定律", "summary": "F=ma"}
        )

        response = await client.post(
            "/api/v1/brainstorm/suggest",
            json={
                "book_id": "book-1",
                "node_id": "node-1",
                "mode": "hint",
                "user_idea": "我想补充受力分析",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["guidance"] == "先想想受力分析"
        assert body["suggestions"] == []
        mock_ai_service.guide_idea.assert_awaited_once()

    async def test_generate_returns_subtree(
        self, client, mock_graph_service, ai_override
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={"id": "node-1", "name": "力学", "summary": ""}
        )

        response = await client.post(
            "/api/v1/brainstorm/suggest",
            json={"book_id": "book-1", "node_id": "node-1", "mode": "generate"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "generate"
        assert body["subtree"][0]["name"] == "受力分析"

    async def test_suggest_node_not_found(self, client, mock_graph_service, ai_override):
        mock_graph_service.get_node_detail = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/brainstorm/suggest",
            json={"book_id": "book-1", "node_id": "nope", "mode": "hint"},
        )

        assert response.status_code == 404

    async def test_generate_degraded(
        self, client, mock_graph_service, mock_ai_service, ai_override
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={"id": "node-1", "name": "力学", "summary": ""}
        )
        mock_ai_service.generate_subtree = AsyncMock(
            return_value={"status": "failed", "message": "AI繁忙，请稍后重试"}
        )

        response = await client.post(
            "/api/v1/brainstorm/suggest",
            json={"book_id": "book-1", "node_id": "node-1", "mode": "generate"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["subtree"] == []

def _parse_sse(raw: str) -> list[dict]:
    """把 SSE 文本拆成事件列表（只关心 data: 行里的 JSON）。"""
    events = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[len("data: "):]))
    return events


class TestSuggestStreamEndpoint:
    """流式构思回归用例。

    背景：hint 分支曾把 pydantic 模型 `BrainstormNode` 直接交给 json.dumps，
    导致 `TypeError: Object of type BrainstormNode is not JSON serializable`。
    异常发生在响应已经开始之后，客户端只收到半截流，界面显示「暂无建议」，
    而模型其实已经返回了结果。这里用「事件序列」把行为钉死。
    """

    async def test_hint_stream_returns_json_suggestions(
        self, client, mock_graph_service, ai_override
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={"id": "node-1", "name": "牛顿第二定律", "summary": "F=ma"}
        )

        response = await client.post(
            "/api/v1/brainstorm/suggest/stream",
            json={"book_id": "book-1", "node_id": "node-1", "mode": "hint"},
        )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert [e["type"] for e in events] == ["start", "suggestions", "done"]
        # 关键断言：建议必须是可 JSON 序列化的结构，而不是被兜底成字符串
        assert events[1]["suggestions"][0]["name"] == "惯性"
        assert isinstance(events[1]["suggestions"][0], dict)

    async def test_guide_stream_emits_deltas(
        self, client, mock_graph_service, mock_ai_service, ai_override
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={"id": "node-1", "name": "牛顿第二定律", "summary": "F=ma"}
        )

        async def _fake_stream(*_args, **_kwargs):
            for chunk in ("先做受力分析，", "再看合力方向"):
                yield chunk

        mock_ai_service.guide_idea_stream = _fake_stream

        response = await client.post(
            "/api/v1/brainstorm/suggest/stream",
            json={
                "book_id": "book-1",
                "node_id": "node-1",
                "mode": "hint",
                "user_idea": "我想补充受力分析",
            },
        )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[0] == {"type": "start", "mode": "guide"}
        text = "".join(e["content"] for e in events if e["type"] == "delta")
        assert text == "先做受力分析，再看合力方向"
        assert events[-1]["type"] == "done"

    async def test_stream_failure_keeps_done_and_hides_internal_error(
        self, client, mock_graph_service, mock_ai_service, ai_override
    ):
        """模型调用抛错时：流必须以 done 收尾，且不能把内部异常原文回传前端。"""
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={"id": "node-1", "name": "牛顿第二定律", "summary": "F=ma"}
        )
        mock_ai_service.suggest_hint = AsyncMock(
            side_effect=RuntimeError("upstream 401 sk-live-should-not-leak")
        )

        response = await client.post(
            "/api/v1/brainstorm/suggest/stream",
            json={"book_id": "book-1", "node_id": "node-1", "mode": "hint"},
        )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1]["type"] == "done"
        assert events[-2]["type"] == "error"
        assert "sk-live-should-not-leak" not in response.text

    async def test_stream_node_not_found(self, client, mock_graph_service, ai_override):
        mock_graph_service.get_node_detail = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/brainstorm/suggest/stream",
            json={"book_id": "book-1", "node_id": "nope", "mode": "hint"},
        )

        assert response.status_code == 404

    async def test_stream_rejects_generate_mode(
        self, client, mock_graph_service, ai_override
    ):
        """流式接口不支持 generate：必须明确报错，不能静默退回 hint。

        generate 返回的是结构化子树，若被当成 hint 处理，调用方会拿到一串
        「建议节点名」而不是子树，看起来成功其实是错的。
        """
        response = await client.post(
            "/api/v1/brainstorm/suggest/stream",
            json={"book_id": "book-1", "node_id": "node-1", "mode": "generate"},
        )

        assert response.status_code == 400
        assert "generate" in response.json()["detail"]


class TestNormalizeNodeType:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("category", "category"),
            ("CATEGORY", "category"),
            ("目录", "category"),
            ("章节", "category"),
            ("knowledge", "knowledge"),
            ("知识点", "knowledge"),
            ("", "knowledge"),
        ],
    )
    def test_node_type_field(self, raw, expected):
        assert _normalize_node_type({"node_type": raw}) == expected

    def test_falls_back_to_type_field(self):
        assert _normalize_node_type({"type": "category"}) == "category"
        assert _normalize_node_type({"type": "method"}) == "knowledge"

    def test_children_hint_marks_category(self):
        assert _normalize_node_type({"children": [{"name": "x"}]}) == "category"

    def test_explicit_knowledge_with_children_upgrades_to_category(self):
        assert (
            _normalize_node_type({"node_type": "knowledge", "children": [{"name": "x"}]})
            == "category"
        )
        assert (
            _normalize_node_type({"type": "concept", "children": [{"name": "x"}]})
            == "category"
        )

    def test_leaf_defaults_to_knowledge(self):
        assert _normalize_node_type({}) == "knowledge"


class TestToNodeNormalization:
    def test_chinese_node_type_is_normalized(self):
        node = _to_node({"name": "力学", "node_type": "目录", "children": []})
        assert node.node_type == "category"

    def test_nested_children_are_converted(self):
        node = _to_node({
            "name": "力学",
            "node_type": "category",
            "children": [{"name": "牛顿第二定律", "node_type": "知识点"}],
        })
        assert node.node_type == "category"
        assert node.children[0].node_type == "knowledge"

    def test_empty_name_falls_back(self):
        assert _to_node({"node_type": "knowledge"}).name == "未命名"
    def test_knowledge_with_children_becomes_category(self):
        node = _to_node({
            "name": "MVCC多版本并发控制",
            "node_type": "knowledge",
            "children": [
                {"name": "MVCC基本原理", "node_type": "knowledge"}
            ],
        })
        assert node.node_type == "category"
