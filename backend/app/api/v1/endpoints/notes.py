import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user_id,
    get_db,
    get_extraction_service,
    get_graph_service,
    get_ocr_service,
)
from app.core.config import settings
from app.core.constants import NOTE_STATUS
from app.core.exceptions import ForbiddenException
from app.core.logger import get_logger
from app.core.upload_guard import read_upload_limited
from app.models.note import Note
from app.schemas.note import NoteList, NoteOut, NoteUpdate
from app.services.extraction_service import ExtractionService
from app.services.ocr_service import OcrError, OcrNotConfiguredError, OcrService

router = APIRouter()
logger = get_logger(__name__)


def _to_out(note: Note, include_content: bool = False) -> NoteOut:
    # 抽取阶段的 nodes_count 含 book 根节点，展示口径与书架保持一致
    # （含目录、不含书根），避免同一份知识在不同页面显示不同数量
    raw_nodes = note.nodes_count or 0
    display_nodes = raw_nodes - 1 if raw_nodes > 0 else 0
    return NoteOut(
        id=note.id,
        title=note.title,
        format=note.format,
        tags=[t for t in note.tags.split(",") if t] if note.tags else [],
        subject=note.subject,
        upload_time=note.upload_time,
        task_id=note.task_id,
        content=note.content if include_content else None,
        status=note.status or NOTE_STATUS["PENDING"],
        nodes_count=display_nodes,
        edges_count=note.edges_count or 0,
        error_message=note.error_message,
        processed_time=note.processed_time,
    )


@router.get("", response_model=NoteList)
async def list_notes(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(
            select(func.count(Note.id)).where(Note.user_id == user_id)
        )
    ).scalar_one()
    offset = (page - 1) * size
    result = await db.execute(
        select(Note)
        .where(Note.user_id == user_id)
        .order_by(Note.upload_time.desc(), Note.id.desc())
        .limit(size)
        .offset(offset)
    )
    notes = result.scalars().all()
    return NoteList(items=[_to_out(n) for n in notes], total=total)


@router.post("/upload", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def upload_note(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject: str | None = Form(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    extraction_service: ExtractionService = Depends(get_extraction_service),
    ocr_service: OcrService = Depends(get_ocr_service),
):
    # 每用户 24 小时上传配额：一次上传 = 一次 LLM 抽取（失败还会重试 3 次），
    # 登录用户侧原本没有任何闸门，是最容易被刷量的入口。
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    uploaded_recently = (
        await db.execute(
            select(func.count(Note.id)).where(
                Note.user_id == user_id,
                Note.upload_time >= since,
            )
        )
    ).scalar_one()
    if (uploaded_recently or 0) >= settings.UPLOAD_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"24 小时内最多上传 {settings.UPLOAD_DAILY_LIMIT} 篇笔记，"
                "请稍后再试（已上传的笔记仍可正常复习）"
            ),
        )

    # 分块读取并在超限时立即中断，避免超大上传先把内存打满（原实现是整体 read 后再比长度）
    content_bytes = await read_upload_limited(file, settings.MAX_FILE_SIZE)
    if not content_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件内容为空，请重新选择",
        )

    filename = file.filename or "untitled"
    ext = os.path.splitext(filename)[1].lower()
    is_image = ext in settings.IMAGE_EXTENSIONS
    allowed = set(settings.ALLOWED_EXTENSIONS) | set(settings.IMAGE_EXTENSIONS)
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}",
        )

    fmt = ext.lstrip(".")

    # 图片先同步 OCR 出正文，识别失败则不入库，避免留下无法处理的空笔记
    text_content = ""
    if is_image:
        try:
            text_content = await ocr_service.recognize_bytes(content_bytes, ext)
        except OcrNotConfiguredError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except OcrError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc

    note_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    # 笔记原始文件放在不对外静态暴露的 notes 子目录
    note_dir = os.path.join(settings.UPLOAD_DIR, "notes")
    os.makedirs(note_dir, exist_ok=True)
    saved_path = os.path.join(note_dir, f"{note_id}{ext}")
    with open(saved_path, "wb") as f:
        f.write(content_bytes)

    if not is_image:
        try:
            from app.services.file_parser import parse_file

            # 文件解析为 CPU/IO 阻塞操作，放到线程池避免阻塞事件循环
            text_content = await asyncio.to_thread(parse_file, saved_path, fmt) or ""
        except Exception:  # noqa: BLE001 - PDF/Word 解析失败时正文留空，由抽取阶段判定为空
            logger.warning(
                "笔记文件解析失败，正文留空 note_id=%s fmt=%s", note_id, fmt, exc_info=True
            )
            text_content = ""

        # 扫描版 PDF / 纯图片 Word 提取不到任何文字。以前会照常入库，
        # 然后由抽取阶段判空失败——用户看到的是一条「失败」的笔记，还得自己猜原因。
        # 这里直接拒绝并说清出路，同时不占用上传配额、不触发任何 LLM 调用。
        if not text_content.strip():
            try:
                os.remove(saved_path)
            except OSError:
                pass
            raise HTTPException(
                status_code=422,
                detail=(
                    "未能从文件中提取到文字，可能是扫描版 PDF 或纯图片文档。"
                    "请上传可复制文本的版本，或把页面截图按图片上传（支持 OCR）。"
                ),
            )

    note = Note(
        id=note_id,
        user_id=user_id,
        title=filename,
        content=text_content,
        format=fmt,
        subject=(subject or "").strip()[:32] or None,
        file_path=saved_path,
        task_id=task_id,
        status=NOTE_STATUS["PENDING"],
        upload_time=datetime.now(timezone.utc),
    )
    db.add(note)
    await db.commit()

    background_tasks.add_task(
        extraction_service.extract_and_build_graph,
        note_id=note_id,
        user_id=user_id,
        file_path=saved_path,
        fmt=fmt,
    )

    return _to_out(note)


@router.post("/{note_id}/re-extract", response_model=NoteOut)
async def re_extract_note(
    note_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    extraction_service: ExtractionService = Depends(get_extraction_service),
):
    from sqlalchemy import select

    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在"
        )
    retryable = note.status in (NOTE_STATUS["FAILED"], NOTE_STATUS["EMPTY"]) or (
        note.status == NOTE_STATUS["SUCCESS"] and not (note.nodes_count or 0)
    )
    if not retryable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅抽取失败或内容为空的笔记支持重新抽取",
        )
    if not note.file_path or not os.path.exists(note.file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原始文件已丢失，无法重新抽取",
        )

    note.status = NOTE_STATUS["PENDING"]
    note.error_message = None
    note.nodes_count = 0
    note.edges_count = 0
    await db.commit()
    await db.refresh(note)

    background_tasks.add_task(
        extraction_service.extract_and_build_graph,
        note_id=note_id,
        user_id=user_id,
        file_path=note.file_path,
        fmt=note.format,
    )

    return _to_out(note)


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    payload: NoteUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    graph_service=Depends(get_graph_service),
):
    """改笔记标题/学科。

    标题会同步写到图谱里对应的书根节点——用户看到书名的地方是书架，
    只改 SQLite 会留下「笔记页叫新名、书架还是旧名」的分裂感。
    """
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在"
        )

    updated = payload.model_dump(exclude_unset=True)

    if "title" in updated:
        title = (updated.get("title") or "").strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空"
            )
        note.title = title[:255]
        try:
            await graph_service.update_book_name_by_note(user_id, note_id, note.title)
        except Exception:  # noqa: BLE001 - 图谱改名失败不该阻塞笔记改名
            logger.warning(
                "同步书根节点名失败 note_id=%s", note_id, exc_info=True
            )

    if "subject" in updated:
        raw = (updated.get("subject") or "").strip()
        note.subject = raw[:32] or None

    await db.commit()
    await db.refresh(note)
    return _to_out(note)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在"
        )
    return _to_out(note, include_content=True)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    graph_service=Depends(get_graph_service),
):
    from sqlalchemy import select

    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在"
        )
    if note.file_path and os.path.exists(note.file_path):
        try:
            os.remove(note.file_path)
        except OSError:
            pass
    try:
        deleted = await graph_service.delete_by_note_id(user_id, note_id)
        if deleted:
            logger.info("删笔记 %s 同步清理图谱节点 %d 个", note_id, deleted)
    except ForbiddenException:
        logger.warning("删笔记 %s：当前为只读演示环境，图谱节点无法自动清理", note_id)
    except Exception:
        logger.exception("删笔记 %s 清理图谱失败，忽略继续", note_id)
    await db.delete(note)
    await db.commit()
