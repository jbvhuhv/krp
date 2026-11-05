from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_extraction_writes_to_graph(tmp_path):
    from app.services.extraction_service import ExtractionService

    note_file = tmp_path / "test.md"
    note_file.write_text("# Machine Learning\nML is a subset of AI.")

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(return_value={
        "nodes": [
            {"name": "Machine Learning", "summary": "ML is a subset of AI", "type": "concept"},
            {"name": "AI", "summary": "Artificial Intelligence", "type": "concept"},
        ],
        "edges": [
            {"source": "Machine Learning", "target": "AI", "relation": "subset_of"},
        ],
    })

    graph_service = AsyncMock()
    graph_service.write_extraction_result = AsyncMock()

    extraction_service = ExtractionService(ai_service=ai_service, graph_service=graph_service)

    await extraction_service.extract_and_build_graph(
        note_id="note-001",
        user_id="user-001",
        file_path=str(note_file),
        fmt="md",
    )

    ai_service.extract_knowledge.assert_called_once()
    graph_service.write_extraction_result.assert_called_once()
    call_kwargs = graph_service.write_extraction_result.call_args.kwargs
    assert call_kwargs["user_id"] == "user-001"
    assert call_kwargs["note_id"] == "note-001"
    assert len(call_kwargs["result"]["nodes"]) == 2
    assert len(call_kwargs["result"]["edges"]) == 1


async def test_node_contains_required_fields():
    from app.services.graph_service import GraphService

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_driver = AsyncMock()
    mock_driver.session = mock_session_ctx

    graph_service = GraphService(driver=mock_driver)
    node_id = await graph_service.create_node(
        user_id="user-001",
        name="Machine Learning",
        summary="ML is a subset of AI",
        type="concept",
        source_note_id="note-001",
    )

    assert node_id
    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args.args[0]
    params = mock_session.run.call_args.kwargs
    assert "KnowledgeNode" in cypher
    assert "source_note_id" in cypher
    assert params["name"] == "Machine Learning"
    assert params["summary"] == "ML is a subset of AI"
    assert params["type"] == "concept"
    assert params["source_note_id"] == "note-001"
    assert params["user_id"] == "user-001"


async def test_write_extraction_result_creates_nodes_and_edges():
    from app.services.graph_service import GraphService

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_driver = AsyncMock()
    mock_driver.session = mock_session_ctx

    graph_service = GraphService(driver=mock_driver)
    result = {
        "nodes": [
            {"name": "A", "summary": "sum A", "type": "concept"},
            {"name": "B", "summary": "sum B", "type": "concept"},
        ],
        "edges": [
            {"source": "A", "target": "B", "relation": "related_to"},
        ],
    }
    await graph_service.write_extraction_result("user-001", "note-001", result)

    # 3 个节点（书 + A + B）+ 2 条 CHILD_OF 边（A/B 挂书）= 5
    # 说明：无 categories 时提前返回，节点间关系边不在此分支创建
    assert mock_session.run.call_count == 5


async def test_ai_service_parse_extraction_response():
    from app.services.ai_service import AIService

    response = '{"nodes": [{"name": "X", "summary": "s", "type": "concept"}], "edges": []}'
    result = AIService._parse_extraction_response(response)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["name"] == "X"
    assert result["edges"] == []


async def test_ai_service_parse_markdown_wrapped_json():
    from app.services.ai_service import AIService

    response = '```json\n{"nodes": [{"name": "Y"}], "edges": []}\n```'
    result = AIService._parse_extraction_response(response)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["name"] == "Y"


async def test_ai_service_parse_invalid_json_returns_empty():
    """解析失败要返回「空但结构完整」的结果。

    结构以当前的 categories 树状格式为准（同 _parse_extraction_response 的 setdefault），
    下游据此判断「这篇笔记没抽到知识」，缺 key 会直接 KeyError。
    """
    from app.services.ai_service import AIService

    result = AIService._parse_extraction_response("not json at all")
    assert result["categories"] == []
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["book_summary"] == ""


async def test_extraction_prompt_formats_with_text():
    """提示词模板占位符可正常填充，且输出契约是 categories 树状结构。

    早期版本要求模型直接返回扁平的 {"nodes": [...]}，后来改成「目录-知识点」树
    （book_summary / subject / categories / edges）。断言若还盯着旧格式，
    模板被改坏也发现不了——这里对齐当前契约。
    """
    from app.services.ai_service import EXTRACTION_PROMPT

    formatted = EXTRACTION_PROMPT.format(text="示例知识")
    assert "示例知识" in formatted
    assert '"categories"' in formatted
    assert '"book_summary"' in formatted


async def test_extract_knowledge_calls_llm_with_formatted_prompt():
    from app.services.ai_service import AIService

    llm = AsyncMock()
    llm.chat = AsyncMock(return_value='{"nodes": [{"name": "A"}], "edges": []}')

    service = AIService(llm=llm)
    result = await service.extract_knowledge("一些知识内容")

    assert result["nodes"][0]["name"] == "A"
    prompt = llm.chat.call_args.args[0]
    assert "一些知识内容" in prompt


async def test_file_parser_parse_markdown(tmp_path):
    from app.services.file_parser import parse_file

    f = tmp_path / "test.md"
    f.write_text("# Hello\nWorld")
    text = parse_file(str(f), "md")
    assert "Hello" in text
    assert "World" in text


async def test_file_parser_parse_txt(tmp_path):
    from app.services.file_parser import parse_file

    f = tmp_path / "test.txt"
    f.write_text("plain text content")
    text = parse_file(str(f), "txt")
    assert text == "plain text content"

async def test_extraction_retries_then_succeeds(tmp_path):
    from app.services.extraction_service import ExtractionService

    note_file = tmp_path / "retry.md"
    note_file.write_text("some content")

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(side_effect=[
        RuntimeError("LLM 超时"),
        {"nodes": [{"name": "重试成功知识点", "summary": "s", "type": "concept"}], "edges": []},
    ])
    graph_service = AsyncMock()
    graph_service.write_extraction_result = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        max_attempts=3,
        backoff_seconds=0,
    )
    result = await service.extract_and_build_graph(
        note_id="note-r", user_id="user-r", file_path=str(note_file), fmt="md"
    )

    assert result["status"] == "success"
    assert ai_service.extract_knowledge.await_count == 2
    graph_service.write_extraction_result.assert_called_once()


async def test_extraction_empty_result_marked_empty(tmp_path):
    from app.services.extraction_service import ExtractionService

    note_file = tmp_path / "empty.md"
    note_file.write_text("some content")

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(
        return_value={"categories": [], "nodes": [], "edges": []}
    )
    graph_service = AsyncMock()
    graph_service.write_extraction_result = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        max_attempts=2,
        backoff_seconds=0,
    )
    result = await service.extract_and_build_graph(
        note_id="note-e", user_id="user-e", file_path=str(note_file), fmt="md"
    )

    assert result["status"] == "empty"
    # 空结果必须带可读原因：界面只有「内容为空」三个字时，用户不知道下一步该做什么
    assert "AI 没能" in result["reason"]
    graph_service.write_extraction_result.assert_not_called()
    assert ai_service.extract_knowledge.await_count == 1


async def test_extraction_returns_failed_after_max_attempts(tmp_path):
    from app.services.extraction_service import ExtractionService

    note_file = tmp_path / "fail.md"
    note_file.write_text("some content")

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(side_effect=RuntimeError("LLM 持续失败"))
    graph_service = AsyncMock()
    graph_service.write_extraction_result = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        max_attempts=2,
        backoff_seconds=0,
    )
    result = await service.extract_and_build_graph(
        note_id="note-f", user_id="user-f", file_path=str(note_file), fmt="md"
    )

    assert result["status"] == "failed"
    # 失败原因不再原样透给用户：上游地址/状态码只进日志，界面只拿可读文案
    assert "LLM 持续失败" not in result["error"]
    assert "http" not in result["error"].lower()
    assert result["error"]
    assert ai_service.extract_knowledge.await_count == 2
    graph_service.write_extraction_result.assert_not_called()


async def test_extraction_error_message_does_not_leak_upstream(tmp_path):
    """上游 401 与接口地址不能出现在用户可见的 error_message 里。"""
    import httpx

    from app.services.extraction_service import ExtractionService, public_error_message

    note_file = tmp_path / "leak.md"
    note_file.write_text("some content")

    request = httpx.Request("POST", "https://maas.example.com/v1/chat/completions")
    response = httpx.Response(401, request=request)
    err = httpx.HTTPStatusError("401 Unauthorized for url", request=request, response=response)

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(side_effect=err)
    graph_service = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        max_attempts=1,
        backoff_seconds=0,
    )
    result = await service.extract_and_build_graph(
        note_id="note-leak", user_id="user-leak", file_path=str(note_file), fmt="md"
    )

    message = public_error_message(err)
    assert result["error"] == message
    assert "example.com" not in message
    assert "401" in message  # 状态码可以留，地址不行


async def test_extraction_retries_on_missing_file(tmp_path):
    from app.services.extraction_service import ExtractionService

    ai_service = AsyncMock()
    graph_service = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        max_attempts=3,
        backoff_seconds=0,
    )
    result = await service.extract_and_build_graph(
        note_id="note-m",
        user_id="user-m",
        file_path=str(tmp_path / "missing.md"),
        fmt="md",
    )

    assert result["status"] == "failed"
    ai_service.extract_knowledge.assert_not_called()


async def test_extraction_skips_empty_file(tmp_path):
    from app.services.extraction_service import ExtractionService

    note_file = tmp_path / "blank.md"
    note_file.write_text("   \n  ")

    ai_service = AsyncMock()
    graph_service = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        backoff_seconds=0,
    )
    result = await service.extract_and_build_graph(
        note_id="note-e", user_id="user-e", file_path=str(note_file), fmt="md"
    )

    assert result["status"] == "empty"
    assert "没有可识别的文字" in result["reason"]
    ai_service.extract_knowledge.assert_not_called()
    graph_service.write_extraction_result.assert_not_called()

async def _make_note_session():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.models.note import Note
    from app.models.user import Base

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            Note(id="n1", user_id="u1", title="t.md", content="x", format="md", status="pending")
        )
        await session.commit()
    return engine, session_factory, Note


async def test_extraction_updates_note_status_success(tmp_path):
    """抽取成功要落库状态与计数。

    nodes_count 现在是「2 个知识点 + 1 个书籍根节点 = 3」：写入图谱时会先建一个
    book 根节点把它们挂起来，旧断言按 2 算，于是这条用例长期挂 xfail。
    这里对齐真实语义，并额外验证根节点确实被计入（否则前端书架统计会少一层）。
    """
    from sqlalchemy import select

    from app.services.extraction_service import ExtractionService

    engine, session_factory, Note = await _make_note_session()
    note_file = tmp_path / "t.md"
    note_file.write_text("Machine Learning and AI")

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(
        return_value={
            "nodes": [{"name": "ML"}, {"name": "AI"}],
            "edges": [{"source": "ML", "target": "AI", "relation": "subset_of"}],
        }
    )
    graph_service = AsyncMock()
    graph_service.write_extraction_result = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        backoff_seconds=0,
        session_factory=session_factory,
    )
    result = await service.extract_and_build_graph("n1", "u1", str(note_file), "md")
    assert result["status"] == "success"

    async with session_factory() as session:
        note = (await session.execute(select(Note).where(Note.id == "n1"))).scalar_one()
        assert note.status == "success"
        # 2 个知识点 + 1 个书籍根节点
        assert note.nodes_count == 3
        assert note.edges_count == 1
        assert note.processed_time is not None
    await engine.dispose()


async def test_extraction_updates_note_status_failed(tmp_path):
    from sqlalchemy import select

    from app.services.extraction_service import ExtractionService

    engine, session_factory, Note = await _make_note_session()
    note_file = tmp_path / "t.md"
    note_file.write_text("content")

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(side_effect=RuntimeError("AI 服务未配置"))
    graph_service = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        max_attempts=2,
        backoff_seconds=0,
        session_factory=session_factory,
    )
    result = await service.extract_and_build_graph("n1", "u1", str(note_file), "md")
    assert result["status"] == "failed"

    async with session_factory() as session:
        note = (await session.execute(select(Note).where(Note.id == "n1"))).scalar_one()
        assert note.status == "failed"
        assert note.error_message and "AI 服务未配置" in note.error_message
    await engine.dispose()

async def test_write_extraction_result_nested_categories():
    from app.services.graph_service import GraphService

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_driver = AsyncMock()
    mock_driver.session = mock_session_ctx

    graph_service = GraphService(driver=mock_driver)
    result = {
        "book_summary": "全书",
        "categories": [
            {
                "name": "C1",
                "summary": "",
                "categories": [
                    {
                        "name": "C1.1",
                        "summary": "",
                        "knowledge_points": [{"name": "K1", "summary": "", "type": "concept"}],
                    },
                ],
                "knowledge_points": [{"name": "K2", "summary": "", "type": "concept"}],
            },
        ],
        "edges": [],
    }
    await graph_service.write_extraction_result("u1", "n1", result)
    # 1 book + 1 C1 + 1 C1.1 + 1 K1 + 1 K2 = 5 个节点
    # CHILD_OF 边：C1/C1.1/K1/K2 各 1 条（书为根不建边）= 4
    assert mock_session.run.call_count == 9


async def test_backfill_edges_when_llm_returns_none():
    from app.services.extraction_service import _backfill_edges

    result = {
        "categories": [
            {
                "name": "C1",
                "knowledge_points": [{"name": "K1"}, {"name": "K2"}, {"name": "K3"}],
                "categories": [],
            },
            {"name": "C2", "knowledge_points": [{"name": "K4"}], "categories": []},
        ],
        "edges": [],
    }
    _backfill_edges(result)
    # C1 内 3 个知识点补 2 条；C2 只有 1 个知识点，不补
    assert len(result["edges"]) == 2
    assert result["edges"][0]["source"] == "K1"
    assert result["edges"][0]["target"] == "K2"
    assert result["edges"][1]["target"] == "K3"


async def test_backfill_edges_keeps_existing_edges():
    from app.services.extraction_service import _backfill_edges

    result = {
        "categories": [{"name": "C1", "knowledge_points": [{"name": "K1"}, {"name": "K2"}], "categories": []}],
        "edges": [{"source": "K1", "target": "K2", "relation": "依赖"}],
    }
    _backfill_edges(result)
    assert result["edges"] == [{"source": "K1", "target": "K2", "relation": "依赖"}]


async def test_backfill_edges_skips_flat_structure():
    from app.services.extraction_service import _backfill_edges

    result = {"nodes": [{"name": "A"}, {"name": "B"}], "edges": []}
    _backfill_edges(result)
    assert result["edges"] == []


async def test_extraction_nodes_count_recursive(tmp_path):
    from app.services.extraction_service import ExtractionService

    note_file = tmp_path / "nested.md"
    note_file.write_text("content")

    ai_service = AsyncMock()
    ai_service.extract_knowledge = AsyncMock(return_value={
        "book_summary": "全书",
        "categories": [
            {
                "name": "C1",
                "summary": "",
                "categories": [
                    {"name": "C1.1", "summary": "", "knowledge_points": [{"name": "K1", "summary": "", "type": "concept"}]},
                ],
                "knowledge_points": [{"name": "K2", "summary": "", "type": "concept"}],
            },
        ],
        "edges": [],
    })
    graph_service = AsyncMock()
    graph_service.write_extraction_result = AsyncMock()

    service = ExtractionService(ai_service=ai_service, graph_service=graph_service)
    result = await service.extract_and_build_graph("n1", "u1", str(note_file), "md")

    # 1 book + 1 C1 + 1 C1.1 + 1 K1 + 1 K2 = 5
    assert result["nodes_count"] == 5


async def test_empty_status_persists_readable_reason(tmp_path):
    """empty 状态要把原因落库——否则前端只能显示「内容为空」，没有下一步线索。"""
    from sqlalchemy import select

    from app.services.extraction_service import ExtractionService

    engine, session_factory, Note = await _make_note_session()
    note_file = tmp_path / "blank.md"
    note_file.write_text("   \n  ")

    service = ExtractionService(
        ai_service=AsyncMock(),
        graph_service=AsyncMock(),
        session_factory=session_factory,
        backoff_seconds=0,
    )
    await service.extract_and_build_graph(
        note_id="n1", user_id="u1", file_path=str(note_file), fmt="md"
    )

    async with session_factory() as session:
        note = (await session.execute(select(Note).where(Note.id == "n1"))).scalar_one()
        assert note.status == "empty"
        assert "没有可识别的文字" in (note.error_message or "")
    await engine.dispose()
