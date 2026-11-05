"""书架导出 Word 思维导图：结构整理 + 接口行为。

关键点：导出的 .docx 必须能被 Word 打开（python-docx 能回读），
且层级缩进要逐级递增，否则"思维导图"就退化成一段平铺文字。
"""

import io

from docx import Document

from app.services.mindmap_export import build_book_forest


def _nodes() -> list[dict]:
    return [
        {"id": "book-1", "name": "计算机网络", "node_type": "book", "parent_id": None},
        {"id": "cat-1", "name": "物理层", "node_type": "category", "parent_id": "book-1"},
        {"id": "k-1", "name": "曼彻斯特编码", "node_type": "knowledge", "parent_id": "cat-1",
         "summary": "**电平跳变** 表示 0 和 1"},
        {"id": "k-2", "name": "香农定理", "node_type": "knowledge", "parent_id": "cat-1"},
        {"id": "cat-2", "name": "网络层", "node_type": "category", "parent_id": "book-1"},
        {"id": "k-3", "name": "IP 地址", "node_type": "knowledge", "parent_id": "cat-2"},
        {"id": "book-2", "name": "操作系统", "node_type": "book", "parent_id": None},
        {"id": "k-4", "name": "进程调度", "node_type": "knowledge", "parent_id": "book-2"},
    ]


def _texts(content: bytes) -> list[str]:
    return [p.text for p in Document(io.BytesIO(content)).paragraphs]


class TestBuildBookForest:
    def test_nests_children_under_book(self):
        forest = build_book_forest(_nodes())
        assert [b["name"] for b in forest] == ["操作系统", "计算机网络"]

        network = next(b for b in forest if b["name"] == "计算机网络")
        assert network["node_count"] == 5
        assert [c["name"] for c in network["children"]] == ["物理层", "网络层"]
        assert [c["name"] for c in network["children"][0]["children"]] == ["曼彻斯特编码", "香农定理"]

    def test_filter_by_book_id(self):
        forest = build_book_forest(_nodes(), "book-2")
        assert len(forest) == 1
        assert forest[0]["name"] == "操作系统"

    def test_unknown_book_id_returns_none(self):
        # None 表示"这本书不存在"，与"存在但没有知识点"的 [] 区分
        assert build_book_forest(_nodes(), "book-not-exist") is None

    def test_book_without_nodes_is_kept(self):
        nodes = [{"id": "book-9", "name": "空书", "node_type": "book"}]
        forest = build_book_forest(nodes)
        assert forest[0]["children"] == []
        assert forest[0]["node_count"] == 0

    def test_parent_cycle_does_not_recurse_forever(self):
        nodes = [
            {"id": "book-1", "name": "环", "node_type": "book"},
            {"id": "cat-1", "name": "A", "node_type": "category", "parent_id": "book-1"},
            {"id": "cat-2", "name": "B", "node_type": "category", "parent_id": "cat-2"},
        ]
        forest = build_book_forest(nodes)
        assert forest[0]["children"][0]["name"] == "A"


class TestExportMindmapEndpoint:
    async def test_returns_docx_with_tree(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap")

        assert response.status_code == 200
        assert "wordprocessingml.document" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

        texts = _texts(response.content)
        assert "我的知识思维导图" in texts
        assert any("计算机网络" in t and "5 个知识点" in t for t in texts)
        assert "◆ 物理层" in texts
        assert "├ 曼彻斯特编码" in texts
        # 同级最后一个节点用 └ 收尾
        assert "└ 香农定理" in texts

    async def test_summary_is_stripped_of_markdown(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap")

        texts = _texts(response.content)
        assert any("电平跳变 表示 0 和 1" in t for t in texts)
        assert not any("**" in t for t in texts)

    async def test_indent_grows_with_depth(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap")
        paragraph_by_text = {p.text: p for p in Document(io.BytesIO(response.content)).paragraphs}

        category = paragraph_by_text["◆ 物理层"]
        knowledge = paragraph_by_text["├ 曼彻斯特编码"]
        assert category.paragraph_format.left_indent < knowledge.paragraph_format.left_indent

    async def test_book_id_limits_scope(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap", params={"book_id": "book-2"})

        assert response.status_code == 200
        texts = _texts(response.content)
        assert any("操作系统" in t for t in texts)
        assert not any("计算机网络" in t for t in texts)

    async def test_unknown_book_returns_404(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap", params={"book_id": "nope"})

        assert response.status_code == 404

    async def test_empty_shelf_still_returns_document(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = []

        response = await client.get("/api/v1/graph/export/mindmap")

        assert response.status_code == 200
        texts = _texts(response.content)
        assert "书架还是空的" in texts
