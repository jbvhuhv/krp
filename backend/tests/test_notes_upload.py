import io

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def small_markdown_file():
    content = b"# Test Note\nThis is a test note about machine learning."
    return ("test.md", content, "text/markdown")


@pytest.fixture
def large_file():
    content = b"x" * (10 * 1024 * 1024 + 1)
    return ("large.txt", content, "text/plain")


async def test_upload_markdown_success(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    resp = await client.post("/api/v1/notes/upload", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"]
    assert data["task_id"] is not None


async def test_upload_txt_success(client):
    content = b"Plain text note content."
    files = {"file": ("note.txt", io.BytesIO(content), "text/plain")}
    resp = await client.post("/api/v1/notes/upload", files=files)
    assert resp.status_code == 201
    assert resp.json()["task_id"] is not None


async def test_upload_file_too_large(client, large_file):
    filename, content, mime = large_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    resp = await client.post("/api/v1/notes/upload", files=files)
    # 超限改由 upload_guard 分块读取时立即中断，返回 413 而非 400（见 upload_guard 模块注释）
    assert resp.status_code == 413
    assert "上限" in resp.json()["detail"]


async def test_upload_unsupported_format(client):
    content = b"binary data"
    files = {"file": ("test.exe", io.BytesIO(content), "application/octet-stream")}
    resp = await client.post("/api/v1/notes/upload", files=files)
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


async def test_upload_triggers_extraction(client, small_markdown_file, mock_extraction_service):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    await client.post("/api/v1/notes/upload", files=files)
    mock_extraction_service.extract_and_build_graph.assert_called_once()


async def test_upload_persists_note_to_db(client, small_markdown_file, test_db):
    from app.models.note import Note

    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    resp = await client.post("/api/v1/notes/upload", files=files)
    note_id = resp.json()["id"]

    from sqlalchemy import select
    result = await test_db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one()
    assert note.title == filename
    assert note.format == "md"

async def test_upload_default_status_is_pending(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    resp = await client.post("/api/v1/notes/upload", files=files)
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


async def test_get_note_returns_content_and_status(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    note_id = (await client.post("/api/v1/notes/upload", files=files)).json()["id"]

    resp = await client.get(f"/api/v1/notes/{note_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["content"] and "machine learning" in data["content"].lower()


async def test_list_notes_includes_status(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    await client.post("/api/v1/notes/upload", files=files)

    resp = await client.get("/api/v1/notes")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "pending"

async def test_upload_runs_extraction_and_updates_status(
    client, test_engine, small_markdown_file
):
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.api.deps import get_extraction_service
    from app.main import app
    from app.services.ai_service import AIService
    from app.services.extraction_service import ExtractionService

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    llm = AsyncMock()
    llm.chat = AsyncMock(
        return_value='{"nodes": [{"name": "机器学习"}], "edges": []}'
    )
    ai_service = AIService(llm=llm)
    graph_service = AsyncMock()
    graph_service.write_extraction_result = AsyncMock()

    service = ExtractionService(
        ai_service=ai_service,
        graph_service=graph_service,
        backoff_seconds=0,
        session_factory=session_factory,
    )
    app.dependency_overrides[get_extraction_service] = lambda: service

    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    note_id = (await client.post("/api/v1/notes/upload", files=files)).json()["id"]

    data = (await client.get(f"/api/v1/notes/{note_id}")).json()
    assert data["status"] == "success"
    # nodes_count 展示口径为「含目录、不含书根」：抽取结果为 book 根 + 1 个节点 = 2，展示减 1
    assert data["nodes_count"] == 1
    assert data["edges_count"] == 0
    graph_service.write_extraction_result.assert_awaited_once()

async def test_upload_image_runs_ocr_and_persists_content(client, test_db):
    from sqlalchemy import select

    from app.models.note import Note

    files = {"file": ("scan.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")}
    resp = await client.post("/api/v1/notes/upload", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert data["format"] == "png"

    note = (await test_db.execute(select(Note).where(Note.id == data["id"]))).scalar_one()
    assert note.content == "识别出的图片文字"


async def test_reextract_failed_note(
    client, small_markdown_file, mock_extraction_service, test_db
):
    from sqlalchemy import select

    from app.models.note import Note

    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    note_id = (await client.post("/api/v1/notes/upload", files=files)).json()["id"]

    note = (await test_db.execute(select(Note).where(Note.id == note_id))).scalar_one()
    note.status = "failed"
    note.error_message = "boom"
    await test_db.commit()

    resp = await client.post(f"/api/v1/notes/{note_id}/re-extract")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["error_message"] is None
    assert mock_extraction_service.extract_and_build_graph.call_count == 2


async def test_reextract_rejects_pending_note(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    note_id = (await client.post("/api/v1/notes/upload", files=files)).json()["id"]

    resp = await client.post(f"/api/v1/notes/{note_id}/re-extract")
    assert resp.status_code == 400
    assert "重新抽取" in resp.json()["detail"]


async def test_reextract_missing_note(client):
    resp = await client.post("/api/v1/notes/does-not-exist/re-extract")
    assert resp.status_code == 404

async def test_list_notes_rejects_oversized_page(client):
    resp = await client.get("/api/v1/notes?size=500")
    assert resp.status_code == 422


async def test_list_notes_respects_page_size(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    for _ in range(3):
        files = {"file": (filename, io.BytesIO(content), mime)}
        await client.post("/api/v1/notes/upload", files=files)

    resp = await client.get("/api/v1/notes?page=1&size=2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_upload_blank_text_is_rejected_before_extraction(client):
    """扫描版 PDF/空白文档提取不到文字时应明确 422，而不是入库后静默失败。"""
    files = {"file": ("scan.txt", io.BytesIO(b"   \n\t  \n"), "text/plain")}
    resp = await client.post("/api/v1/notes/upload", files=files)
    assert resp.status_code == 422
    assert "提取到文字" in resp.json()["detail"]


async def test_upload_with_subject_persists(client, small_markdown_file, test_db):
    """上传时选的学科要落库——否则抽取模型判错就得重传一次。"""
    from sqlalchemy import select

    from app.models.note import Note

    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    resp = await client.post(
        "/api/v1/notes/upload", files=files, data={"subject": "计算机体系结构"}
    )

    assert resp.status_code == 201
    assert resp.json()["subject"] == "计算机体系结构"
    note = (
        await test_db.execute(select(Note).where(Note.id == resp.json()["id"]))
    ).scalar_one()
    assert note.subject == "计算机体系结构"


async def test_upload_without_subject_stays_null(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    resp = await client.post("/api/v1/notes/upload", files=files)

    assert resp.status_code == 201
    assert resp.json()["subject"] is None


async def test_patch_note_title_syncs_book_name(
    client, small_markdown_file, mock_graph_service
):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    note_id = (await client.post("/api/v1/notes/upload", files=files)).json()["id"]

    resp = await client.patch(
        f"/api/v1/notes/{note_id}", json={"title": "数据结构 · 期末复习"}
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "数据结构 · 期末复习"
    # 书架里的书名来自图谱书根节点，必须同步改，否则两个页面显示不一致
    mock_graph_service.update_book_name_by_note.assert_awaited_once()
    args = mock_graph_service.update_book_name_by_note.await_args
    assert args[0][1] == note_id
    assert args[0][2] == "数据结构 · 期末复习"


async def test_patch_note_title_rejects_blank(client, small_markdown_file):
    filename, content, mime = small_markdown_file
    files = {"file": (filename, io.BytesIO(content), mime)}
    note_id = (await client.post("/api/v1/notes/upload", files=files)).json()["id"]

    resp = await client.patch(f"/api/v1/notes/{note_id}", json={"title": "   "})

    assert resp.status_code == 400


async def test_patch_unknown_note_returns_404(client):
    resp = await client.patch("/api/v1/notes/not-exist", json={"title": "x"})
    assert resp.status_code == 404
