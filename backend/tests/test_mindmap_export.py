"""书架导出 Word 思维导图：结构整理 + 接口行为。

关键点：
1. .docx 必须能被 Word 打开（python-docx 能回读）；
2. 连线要贯通到书名（"│ ├"），不是每层都从行首重开，否则看不出脉络；
3. 选书导出要能在参数里多选，且一本书都没匹配上时返回 404。
"""

import io

from docx import Document

from app.services.mindmap_export import build_book_forest


def _nodes() -> list[dict]:
    return [
        {"id": "book-1", "name": "计算机网络", "node_type": "book", "parent_id": None},
        {"id": "cat-1", "name": "物理层", "node_type": "category", "parent_id": "book-1",
         "summary": "物理层的编码与定理"},
        {"id": "k-1", "name": "曼彻斯特编码", "node_type": "knowledge", "parent_id": "cat-1",
         "summary": "**电平跳变** 表示 0 和 1"},
        {"id": "k-2", "name": "香农定理", "node_type": "knowledge", "parent_id": "cat-1"},
        {"id": "cat-2", "name": "网络层", "node_type": "category", "parent_id": "book-1"},
        {"id": "k-3", "name": "IP 地址", "node_type": "knowledge", "parent_id": "cat-2"},
        {"id": "book-2", "name": "操作系统", "node_type": "book", "parent_id": None},
        {"id": "k-4", "name": "进程调度", "node_type": "knowledge", "parent_id": "book-2"},
    ]


def _paragraphs(content: bytes) -> list:
    return list(Document(io.BytesIO(content)).paragraphs)


def _texts(content: bytes) -> list[str]:
    return [p.text for p in _paragraphs(content)]


class TestBuildBookForest:
    def test_nests_children_under_book(self):
        forest = build_book_forest(_nodes())
        assert [b["name"] for b in forest] == ["操作系统", "计算机网络"]

        network = next(b for b in forest if b["name"] == "计算机网络")
        assert network["node_count"] == 5
        assert [c["name"] for c in network["children"]] == ["物理层", "网络层"]
        assert [c["name"] for c in network["children"][0]["children"]] == ["曼彻斯特编码", "香农定理"]

    def test_filter_by_single_book_id(self):
        forest = build_book_forest(_nodes(), ["book-2"])
        assert len(forest) == 1
        assert forest[0]["name"] == "操作系统"

    def test_filter_by_multiple_book_ids(self):
        forest = build_book_forest(_nodes(), ["book-1", "book-2"])
        assert [b["name"] for b in forest] == ["操作系统", "计算机网络"]

    def test_accepts_bare_string_for_backward_compat(self):
        forest = build_book_forest(_nodes(), "book-2")
        assert [b["name"] for b in forest] == ["操作系统"]

    def test_unknown_book_id_returns_none(self):
        # None 表示"这本书不存在"，与"存在但没有知识点"的空 children 区分
        assert build_book_forest(_nodes(), ["book-not-exist"]) is None

    def test_partially_matched_ids_still_export(self):
        # 书被删了但另一个还在：能导就导，不因为一个失效 id 整份失败
        forest = build_book_forest(_nodes(), ["book-1", "book-deleted"])
        assert [b["name"] for b in forest] == ["计算机网络"]

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
        assert "└ 网络层" in texts

    async def test_connector_lines_run_through_levels(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap")
        texts = _texts(response.content)

        # 物理层不是最后一个分支 → 它的子节点前面要带竖线
        assert "├ 物理层" in texts
        assert "│ ├ 曼彻斯特编码" in texts
        assert "│ └ 香农定理" in texts
        # 网络层是最后一个分支 → 子层用空格让位，竖线不再向下延伸
        assert "  └ IP 地址" in texts

    async def test_summary_is_stripped_of_markdown(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap")

        texts = _texts(response.content)
        assert any("电平跳变 表示 0 和 1" in t for t in texts)
        assert not any("**" in t for t in texts)

    async def test_summary_indent_grows_with_depth(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get("/api/v1/graph/export/mindmap")
        by_text = {p.text: p for p in _paragraphs(response.content)}

        category_note = by_text["物理层的编码与定理"]
        knowledge_note = by_text["电平跳变 表示 0 和 1"]
        assert (
            category_note.paragraph_format.left_indent
            < knowledge_note.paragraph_format.left_indent
        )

    async def test_book_ids_limits_scope(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get(
            "/api/v1/graph/export/mindmap",
            params=[("book_ids", "book-2")],
        )

        assert response.status_code == 200
        texts = _texts(response.content)
        assert any("操作系统" in t for t in texts)
        assert not any("计算机网络" in t for t in texts)

    async def test_multiple_book_ids_are_all_exported(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get(
            "/api/v1/graph/export/mindmap",
            params=[("book_ids", "book-1"), ("book_ids", "book-2")],
        )

        assert response.status_code == 200
        texts = _texts(response.content)
        assert any("计算机网络" in t for t in texts)
        assert any("操作系统" in t for t in texts)

    async def test_single_book_filename_uses_book_name(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get(
            "/api/v1/graph/export/mindmap", params=[("book_ids", "book-2")]
        )

        disposition = response.headers["content-disposition"]
        assert "filename*=UTF-8''" in disposition
        assert "%E6%93%8D%E4%BD%9C%E7%B3%BB%E7%BB%9F" in disposition  # "操作系统"

    async def test_unknown_book_returns_404(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = _nodes()

        response = await client.get(
            "/api/v1/graph/export/mindmap", params=[("book_ids", "nope")]
        )

        assert response.status_code == 404

    async def test_empty_shelf_still_returns_document(self, client, mock_graph_service):
        mock_graph_service.get_all_nodes.return_value = []

        response = await client.get("/api/v1/graph/export/mindmap")

        assert response.status_code == 200
        texts = _texts(response.content)
        assert "书架还是空的" in texts
