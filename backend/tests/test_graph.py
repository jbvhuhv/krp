from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.graph_service import GraphService


def async_iter(items):
    async def _aiter():
        for item in items:
            yield item
    return _aiter()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.run = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    return session


@pytest.fixture
def mock_driver(mock_session):
    driver = MagicMock()
    driver.session = MagicMock(return_value=mock_session)
    return driver


@pytest.fixture
def graph_service(mock_driver):
    return GraphService(driver=mock_driver)


class TestGraphServiceCreateNode:
    async def test_create_node_returns_uuid(self, graph_service, mock_session):
        result_mock = AsyncMock()
        mock_session.run.return_value = result_mock

        node_id = await graph_service.create_node(
            user_id="user-1",
            name="牛顿第二定律",
            summary="F=ma",
            type="concept",
            subject="物理",
        )

        assert node_id is not None
        assert len(node_id) == 36
        mock_session.run.assert_called_once()
        cypher = mock_session.run.call_args[0][0]
        assert "CREATE (n:KnowledgeNode" in cypher
        assert "type: $type" in cypher

    async def test_create_node_with_source_note(self, graph_service, mock_session):
        mock_session.run.return_value = AsyncMock()

        node_id = await graph_service.create_node(
            user_id="user-1",
            name="力的合成",
            summary="多个力可合成为一个合力",
            type="concept",
            source_note_id="note-123",
            subject="物理",
        )

        assert node_id is not None
        kwargs = mock_session.run.call_args.kwargs
        assert kwargs["source_note_id"] == "note-123"

    async def test_create_node_with_parent_creates_child_of_edge(
        self, graph_service, mock_session
    ):
        mock_session.run.return_value = AsyncMock()

        await graph_service.create_node(
            user_id="user-1",
            name="子节点",
            summary="",
            type="concept",
            parent_id="parent-1",
        )

        assert mock_session.run.call_count == 2
        edge_cypher = mock_session.run.call_args_list[1].args[0]
        assert "CHILD_OF" in edge_cypher

    async def test_create_node_without_parent_no_edge(
        self, graph_service, mock_session
    ):
        mock_session.run.return_value = AsyncMock()

        await graph_service.create_node(
            user_id="user-1", name="根节点", summary="", type="concept"
        )

        assert mock_session.run.call_count == 1


class TestGraphServiceCreateEdge:
    async def test_create_edge_returns_uuid(self, graph_service, mock_session):
        mock_session.run.return_value = AsyncMock()

        edge_id = await graph_service.create_edge(
            user_id="user-1",
            source_id="node-a",
            target_id="node-b",
            relation="prerequisite_for",
        )

        assert edge_id is not None
        assert len(edge_id) == 36
        cypher = mock_session.run.call_args[0][0]
        assert "RELATED_TO" in cypher

    async def test_create_edge_default_relation(self, graph_service, mock_session):
        mock_session.run.return_value = AsyncMock()

        await graph_service.create_edge(
            user_id="user-1",
            source_id="node-a",
            target_id="node-b",
        )

        kwargs = mock_session.run.call_args.kwargs
        assert kwargs["relation"] == "related_to"


class TestGraphServiceGetUserGraph:
    async def test_get_user_graph_returns_nodes_and_edges(self, graph_service, mock_session):
        node_result = AsyncMock()
        node_record1 = MagicMock()
        node_record1.__getitem__ = MagicMock(return_value={
            "id": "node-1", "user_id": "u1", "name": "A", "summary": "",
            "type": "concept", "subject": None, "source_note_id": None, "mastery": 0.0,
        })
        node_result.__aiter__ = MagicMock(return_value=async_iter([node_record1]))
        node_result.single = AsyncMock(return_value=None)

        edge_result = AsyncMock()
        edge_record = MagicMock()
        edge_record.__getitem__ = MagicMock(side_effect=lambda key: {
            "source_id": "node-1", "target_id": "node-2",
            "relation": "related_to", "weight": 1.0, "edge_id": "edge-1",
        }[key])
        edge_record.get = MagicMock(return_value=1.0)
        edge_result.__aiter__ = MagicMock(return_value=async_iter([]))

        mock_session.run.side_effect = [node_result, edge_result]

        data = await graph_service.get_user_graph("u1")

        assert "nodes" in data
        assert "edges" in data

    async def test_get_user_graph_with_subject_filter(self, graph_service, mock_session):
        node_result = AsyncMock()
        node_result.__aiter__ = MagicMock(return_value=async_iter([]))

        edge_result = AsyncMock()
        edge_result.__aiter__ = MagicMock(return_value=async_iter([]))

        mock_session.run.side_effect = [node_result, edge_result]

        await graph_service.get_user_graph("u1", subject="物理")

        first_call_kwargs = mock_session.run.call_args_list[0].kwargs
        assert first_call_kwargs["subject"] == "物理"


class TestGraphServiceUpdateNode:
    async def test_update_node_no_updates_returns_current(self, graph_service):
        graph_service.get_node_detail = AsyncMock(return_value={"id": "n1", "name": "old"})

        result = await graph_service.update_node("u1", "n1")

        assert result == {"id": "n1", "name": "old"}

    async def test_update_node_with_fields(self, graph_service, mock_session):
        result_mock = AsyncMock()
        record = MagicMock()
        record.__getitem__ = MagicMock(return_value={"id": "n1", "name": "new"})
        result_mock.single = AsyncMock(return_value=record)
        mock_session.run.return_value = result_mock

        result = await graph_service.update_node("u1", "n1", name="new", summary="updated")

        assert result is not None
        cypher = mock_session.run.call_args[0][0]
        assert "SET" in cypher
        kwargs = mock_session.run.call_args.kwargs
        assert kwargs["name"] == "new"
        assert kwargs["summary"] == "updated"

    async def test_update_node_parent_relinks_child_of_edge(
        self, graph_service, mock_session
    ):
        result_mock = AsyncMock()
        record = MagicMock()
        record.__getitem__ = MagicMock(return_value={"id": "n1", "parent_id": "p2"})
        result_mock.single = AsyncMock(return_value=record)
        mock_session.run.return_value = result_mock

        await graph_service.update_node("u1", "n1", parent_id="p2")

        assert mock_session.run.call_count == 3
        relink_cyphers = " ".join(
            call.args[0] for call in mock_session.run.call_args_list
        )
        assert "CHILD_OF" in relink_cyphers


class TestGraphServiceDeleteNode:
    async def test_delete_node_success(self, graph_service, mock_session):
        result_mock = AsyncMock()
        result_mock.single = AsyncMock(return_value=MagicMock())
        mock_session.run.return_value = result_mock

        deleted = await graph_service.delete_node("u1", "n1")

        assert deleted is True

    async def test_delete_node_not_found(self, graph_service, mock_session):
        result_mock = AsyncMock()
        result_mock.single = AsyncMock(return_value=None)
        mock_session.run.return_value = result_mock

        deleted = await graph_service.delete_node("u1", "n1")

        assert deleted is False


class TestGraphServiceDeleteSubtree:
    async def test_delete_subtree_returns_deleted_count(self, graph_service, mock_session):
        result_mock = AsyncMock()
        record = MagicMock()
        record.__getitem__ = MagicMock(return_value=3)
        result_mock.single = AsyncMock(return_value=record)
        mock_session.run.return_value = result_mock

        deleted = await graph_service.delete_subtree("u1", "n1")

        assert deleted == 3

    async def test_delete_subtree_not_found_returns_zero(self, graph_service, mock_session):
        result_mock = AsyncMock()
        result_mock.single = AsyncMock(return_value=None)
        mock_session.run.return_value = result_mock

        deleted = await graph_service.delete_subtree("u1", "n1")

        assert deleted == 0


class TestGraphAPIGetGraph:
    async def test_get_own_graph_success(self, client, mock_graph_service):
        mock_graph_service.get_user_graph = AsyncMock(return_value={
            "nodes": [], "edges": [],
        })

        response = await client.get("/api/v1/graph/test-user-0001")

        assert response.status_code == 200
        assert "nodes" in response.json()
        assert "edges" in response.json()

    async def test_get_other_user_graph_forbidden(self, client):
        response = await client.get("/api/v1/graph/other-user-id")

        assert response.status_code == 403
        assert "无权" in response.json()["detail"]

    async def test_get_graph_with_subject_filter(self, client, mock_graph_service):
        mock_graph_service.get_user_graph = AsyncMock(return_value={
            "nodes": [], "edges": [],
        })

        response = await client.get("/api/v1/graph/test-user-0001?subject=物理")

        assert response.status_code == 200
        call_kwargs = mock_graph_service.get_user_graph.call_args.kwargs
        assert call_kwargs["subject"] == "物理"


class TestGraphAPICreateNode:
    async def test_create_node_success(self, client, mock_graph_service):
        mock_graph_service.create_node = AsyncMock(return_value="new-node-id")

        response = await client.post("/api/v1/graph/nodes", json={
            "name": "牛顿第二定律",
            "summary": "F=ma",
            "type": "concept",
            "subject": "物理",
        })

        assert response.status_code == 201
        body = response.json()
        assert body["id"] == "new-node-id"
        assert body["name"] == "牛顿第二定律"

    async def test_create_node_minimal(self, client, mock_graph_service):
        mock_graph_service.create_node = AsyncMock(return_value="new-node-id")

        response = await client.post("/api/v1/graph/nodes", json={
            "name": "测试节点",
        })

        assert response.status_code == 201


class TestGraphAPICreateCategoryKnowledge:
    async def test_create_category_inherits_from_parent(
        self, client, mock_graph_service
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={
                "id": "book-1",
                "subject": "物理",
                "source_note_id": "note-1",
            }
        )
        mock_graph_service.create_node = AsyncMock(return_value="cat-1")

        response = await client.post("/api/v1/graph/categories", json={
            "name": "力学",
            "parent_id": "book-1",
        })

        assert response.status_code == 201
        body = response.json()
        assert body["subject"] == "物理"
        assert body["source_note_id"] == "note-1"
        _, kwargs = mock_graph_service.create_node.await_args
        assert kwargs["subject"] == "物理"
        assert kwargs["source_note_id"] == "note-1"
        assert kwargs["node_type"] == "category"

    async def test_create_category_explicit_values_skip_lookup(
        self, client, mock_graph_service
    ):
        mock_graph_service.get_node_detail = AsyncMock(return_value=None)
        mock_graph_service.create_node = AsyncMock(return_value="cat-1")

        response = await client.post("/api/v1/graph/categories", json={
            "name": "力学",
            "parent_id": "book-1",
            "subject": "数学",
            "source_note_id": "note-9",
        })

        assert response.status_code == 201
        body = response.json()
        assert body["subject"] == "数学"
        assert body["source_note_id"] == "note-9"
        mock_graph_service.get_node_detail.assert_not_awaited()

    async def test_create_knowledge_inherits_from_parent(
        self, client, mock_graph_service
    ):
        mock_graph_service.get_node_detail = AsyncMock(
            return_value={
                "id": "cat-1",
                "subject": "物理",
                "source_note_id": "note-1",
            }
        )
        mock_graph_service.create_node = AsyncMock(return_value="kp-1")

        response = await client.post("/api/v1/graph/knowledge", json={
            "name": "牛顿第二定律",
            "parent_id": "cat-1",
            "type": "method",
        })

        assert response.status_code == 201
        body = response.json()
        assert body["subject"] == "物理"
        assert body["source_note_id"] == "note-1"
        assert body["type"] == "method"
        _, kwargs = mock_graph_service.create_node.await_args
        assert kwargs["subject"] == "物理"
        assert kwargs["source_note_id"] == "note-1"
        assert kwargs["node_type"] == "knowledge"

    async def test_create_knowledge_no_parent_no_lookup(
        self, client, mock_graph_service
    ):
        mock_graph_service.get_node_detail = AsyncMock(return_value=None)
        mock_graph_service.create_node = AsyncMock(return_value="kp-1")

        response = await client.post("/api/v1/graph/knowledge", json={
            "name": "孤立知识点",
        })

        assert response.status_code == 201
        body = response.json()
        assert body["subject"] is None
        assert body["source_note_id"] is None
        mock_graph_service.get_node_detail.assert_not_awaited()


class TestGraphAPIUpdateNode:
    async def test_update_node_success(self, client, mock_graph_service):
        mock_graph_service.update_node = AsyncMock(return_value={
            "id": "node-1", "name": "updated", "summary": "new summary",
            "type": "concept", "subject": "物理", "mastery": 0.5,
            "source_note_id": None,
        })

        response = await client.put("/api/v1/graph/nodes/node-1", json={
            "name": "updated",
            "summary": "new summary",
        })

        assert response.status_code == 200
        assert response.json()["name"] == "updated"

    async def test_update_node_not_found(self, client, mock_graph_service):
        mock_graph_service.update_node = AsyncMock(return_value=None)

        response = await client.put("/api/v1/graph/nodes/nonexistent", json={
            "name": "x",
        })

        assert response.status_code == 404

    async def test_update_book_name_syncs_note_title(self, client, test_db, mock_graph_service):
        from app.models.note import Note
        from tests.conftest import TEST_USER_ID

        note = Note(
            id="note-sync-1",
            user_id=TEST_USER_ID,
            title="旧书名.md",
            content="正文",
        )
        test_db.add(note)
        await test_db.commit()

        mock_graph_service.update_node = AsyncMock(return_value={
            "id": "book-sync-1", "name": "新书名", "summary": "",
            "type": "book", "subject": None, "node_type": "book",
            "parent_id": None, "mastery": 0.0,
            "source_note_id": "note-sync-1",
        })

        response = await client.put(
            "/api/v1/graph/nodes/book-sync-1", json={"name": "新书名"}
        )

        assert response.status_code == 200
        test_db.expire_all()
        refreshed = await test_db.get(Note, "note-sync-1")
        assert refreshed.title == "新书名"

    async def test_update_non_book_name_keeps_note_title(self, client, test_db, mock_graph_service):
        from app.models.note import Note
        from tests.conftest import TEST_USER_ID

        note = Note(
            id="note-sync-2",
            user_id=TEST_USER_ID,
            title="笔记原标题",
            content="正文",
        )
        test_db.add(note)
        await test_db.commit()

        mock_graph_service.update_node = AsyncMock(return_value={
            "id": "kp-sync-1", "name": "新知识点名", "summary": "",
            "type": "concept", "subject": None, "node_type": "knowledge",
            "parent_id": None, "mastery": 0.0,
            "source_note_id": "note-sync-2",
        })

        response = await client.put(
            "/api/v1/graph/nodes/kp-sync-1", json={"name": "新知识点名"}
        )

        assert response.status_code == 200
        test_db.expire_all()
        refreshed = await test_db.get(Note, "note-sync-2")
        assert refreshed.title == "笔记原标题"


class TestGraphAPIDeleteNode:
    async def test_delete_node_success(self, client, mock_graph_service):
        mock_graph_service.delete_subtree = AsyncMock(return_value=1)

        response = await client.delete("/api/v1/graph/nodes/node-1")

        assert response.status_code == 204

    async def test_delete_node_not_found(self, client, mock_graph_service):
        mock_graph_service.delete_subtree = AsyncMock(return_value=0)

        response = await client.delete("/api/v1/graph/nodes/nonexistent")

        assert response.status_code == 404


class TestGraphAPICreateEdge:
    async def test_create_edge_success(self, client, mock_graph_service):
        mock_graph_service.create_edge = AsyncMock(return_value="new-edge-id")

        response = await client.post("/api/v1/graph/edges", json={
            "source_id": "node-a",
            "target_id": "node-b",
            "relation": "prerequisite_for",
        })

        assert response.status_code == 201
        body = response.json()
        assert body["id"] == "new-edge-id"
        assert body["source_id"] == "node-a"

    async def test_create_edge_default_relation(self, client, mock_graph_service):
        mock_graph_service.create_edge = AsyncMock(return_value="new-edge-id")

        response = await client.post("/api/v1/graph/edges", json={
            "source_id": "node-a",
            "target_id": "node-b",
        })

        assert response.status_code == 201
        assert response.json()["relation"] == "related_to"


class TestGraphAPIGetNodeSource:
    async def test_get_node_source_with_note(self, client, mock_graph_service, test_db):
        from app.models.note import Note
        note = Note(
            id="note-source-1",
            user_id="test-user-0001",
            title="原始笔记",
            format="txt",
            file_path="/uploads/test.txt",
            content="笔记内容",
        )
        test_db.add(note)
        await test_db.commit()

        mock_graph_service.get_node_detail = AsyncMock(return_value={
            "id": "node-1", "source_note_id": "note-source-1",
            "name": "N", "summary": "", "type": "concept",
        })

        response = await client.get("/api/v1/graph/nodes/node-1/source")

        assert response.status_code == 200
        body = response.json()
        assert body["node_id"] == "node-1"
        assert body["source_note"] is not None
        assert body["source_note"]["title"] == "原始笔记"

    async def test_get_node_source_no_source_note(self, client, mock_graph_service):
        mock_graph_service.get_node_detail = AsyncMock(return_value={
            "id": "node-1", "source_note_id": None,
            "name": "N", "summary": "", "type": "concept",
        })

        response = await client.get("/api/v1/graph/nodes/node-1/source")

        assert response.status_code == 200
        assert response.json()["source_note"] is None

    async def test_get_node_source_node_not_found(self, client, mock_graph_service):
        mock_graph_service.get_node_detail = AsyncMock(return_value=None)

        response = await client.get("/api/v1/graph/nodes/nonexistent/source")

        assert response.status_code == 404


class TestWriteExtractionResultDedupe:
    """同一笔记内同名概念只落一个节点。

    实测线上数据里「进程」「死锁」这类概念被模型在多个章节重复列出，
    逐条落库会让知识点数虚高，分身的引用来源还会出现一排同名条目。
    """

    async def _run(self, graph_service, result, book_title="操作系统"):
        calls = []

        async def fake_create_node(**kwargs):
            calls.append(kwargs)
            return f"node-{len(calls)}"

        graph_service.create_node = fake_create_node
        graph_service.create_edge = AsyncMock()
        created = await graph_service.write_extraction_result(
            user_id="u1", note_id="n1", result=result, book_title=book_title
        )
        return calls, created

    async def test_duplicate_categories_and_points_collapse(self, graph_service):
        result = {
            "categories": [
                {"name": "进程与线程", "knowledge_points": [{"name": "进程"}, {"name": "死锁"}]},
                {"name": "进程与线程", "knowledge_points": [{"name": "进程"}, {"name": "死锁"}]},
                {"name": "死锁", "knowledge_points": [{"name": "死锁"}]},
            ],
            "edges": [{"source": "进程", "target": "死锁", "relation": "related_to"}],
        }

        calls, created = await self._run(graph_service, result)

        names = [c["name"] for c in calls]
        # 书根 + 「进程与线程」目录 + 「死锁」目录 + 进程知识点 + 死锁知识点 = 5
        assert created == 5
        assert names.count("进程与线程") == 1
        assert names.count("进程") == 1
        assert names.count("死锁") == 2  # 1 个目录 + 1 个知识点，同名不同类型不互吞

    async def test_edges_still_connect_deduped_nodes(self, graph_service):
        result = {
            "categories": [
                {"name": "A", "knowledge_points": [{"name": "甲"}]},
                {"name": "B", "knowledge_points": [{"name": "甲"}, {"name": "乙"}]},
            ],
            "edges": [{"source": "甲", "target": "乙", "relation": "related_to"}],
        }

        calls, _ = await self._run(graph_service, result)

        graph_service.create_edge.assert_awaited_once()
        kwargs = graph_service.create_edge.await_args.kwargs
        # 边要连到被合并后保留的那个「甲」，而不是重新建出来的副本
        assert kwargs["source_id"] == "node-3"
        # 建节点顺序：书根→目录A→甲→目录B→乙，甲的第二次出现被跳过，所以乙是 node-5
        assert kwargs["target_id"] == "node-5"

    async def test_flat_nodes_dedupe(self, graph_service):
        result = {
            "nodes": [{"name": "梯度下降"}, {"name": "梯度下降"}, {"name": "学习率"}],
            "edges": [],
        }

        calls, created = await self._run(graph_service, result, book_title="机器学习")

        names = [c["name"] for c in calls]
        assert names.count("梯度下降") == 1
        assert created == 3  # 书根 + 2 个不同知识点


class TestCreateNodeTypeInference:
    """建节点漏传 node_type 时按 type 推导。

    书架按 node_type='book' 查询，过去默认死写 knowledge，
    于是「建书成功但书架里看不到」，属于最难排查的一类坑。
    """

    async def test_book_type_without_node_type_becomes_book(
        self, client, mock_graph_service
    ):
        resp = await client.post(
            "/api/v1/graph/nodes",
            json={"name": "操作系统", "type": "book"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["node_type"] == "book"
        kwargs = mock_graph_service.create_node.await_args.kwargs
        assert kwargs["node_type"] == "book"

    async def test_concept_type_without_node_type_stays_knowledge(
        self, client, mock_graph_service
    ):
        resp = await client.post(
            "/api/v1/graph/nodes",
            json={"name": "进程调度", "type": "concept"},
        )

        assert resp.status_code == 201
        assert resp.json()["node_type"] == "knowledge"

    async def test_explicit_node_type_wins(self, client, mock_graph_service):
        resp = await client.post(
            "/api/v1/graph/nodes",
            json={"name": "自定义分类", "type": "concept", "node_type": "category"},
        )

        assert resp.status_code == 201
        assert resp.json()["node_type"] == "category"
