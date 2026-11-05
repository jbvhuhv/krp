"""示例数据一键体验接口（POST /demo/bootstrap）的行为验证。

mock_graph_service 是 AsyncMock：get_books 默认返回 Mock 值，
demo 端点用它判断「书架是否已有数据」，用例里显式覆写。
"""

from app.api.deps import get_graph_service


class TestDemoBootstrap:
    async def test_bootstrap_creates_sample_book_and_note(
        self, client, mock_graph_service, test_db
    ):
        from app.models.note import Note
        from sqlalchemy import select

        async def empty_books(user_id):
            return []  # 空书架 → 允许引导

        async def all_nodes(user_id):
            # 名称 → id 映射：样例边依据名称重建
            return [
                {"id": f"node-{name}", "name": name}
                for name in ["协议三要素", "计算机网络"]
            ]

        mock_graph_service.get_books = empty_books
        mock_graph_service.get_all_nodes = all_nodes

        response = await client.post("/api/v1/demo/bootstrap")
        assert response.status_code == 200
        body = response.json()
        assert body["bootstrapped"] is True
        # 1 书 + 2 章 + 8 知识点
        assert body["nodes_count"] == 11
        assert body["edges_count"] > 0

        create_node = mock_graph_service.create_node
        assert create_node.await_count == 11
        # 第一次调用创建的是书节点
        first_kwargs = create_node.await_args_list[0].kwargs
        assert first_kwargs["node_type"] == "book"
        assert first_kwargs["origin"] == "demo"

        # SQLite 侧落了一条 success 笔记，且 nodes_count 与图谱一致
        result = await test_db.execute(select(Note))
        notes = list(result.scalars().all())
        assert len(notes) == 1
        assert notes[0].status == "success"
        assert notes[0].nodes_count == 11
        assert notes[0].id == body["note_id"]

    async def test_bootstrap_skipped_when_books_exist(
        self, client, mock_graph_service
    ):
        async def existing_books(user_id):
            return [{"id": "book-1", "name": "已有书", "node_count": 5}]

        mock_graph_service.get_books = existing_books
        mock_graph_service.create_node.reset_mock()

        response = await client.post("/api/v1/demo/bootstrap")
        assert response.status_code == 200
        body = response.json()
        assert body["bootstrapped"] is False
        assert mock_graph_service.create_node.await_count == 0

    async def test_bootstrap_graph_failure_returns_503(
        self, client, mock_graph_service
    ):
        async def fail_create_node(**kwargs):
            raise RuntimeError("neo4j down")

        async def empty_books(user_id):
            return []

        mock_graph_service.get_books = empty_books
        mock_graph_service.create_node = fail_create_node

        response = await client.post("/api/v1/demo/bootstrap")
        assert response.status_code == 503
