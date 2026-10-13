import asyncio
from datetime import datetime, timezone

from app.core.config import settings
from app.core.constants import NOTE_STATUS
from app.core.logger import get_logger
from app.services.ai_service import AIService
from app.services.file_parser import parse_file
from app.services.graph_service import GraphService

logger = get_logger(__name__)


def _backfill_edges(result: dict) -> None:
    """LLM 未产出任何关系时，按同一目录内知识点顺序补边，避免图谱零连线。

    仅处理 categories 树状结构（扁平结构在落库时本就不写关系边）。
    """
    if result.get("edges") or not result.get("categories"):
        return
    scopes: list[list[str]] = []

    def _walk(cats: list[dict]) -> None:
        for cat in cats:
            names = [
                kp.get("name")
                for kp in cat.get("knowledge_points", [])
                if kp.get("name")
            ]
            if len(names) > 1:
                scopes.append(names)
            _walk(cat.get("categories", []))

    _walk(result["categories"])
    edges = [
        {"source": src, "target": tgt, "relation": "相关"}
        for names in scopes
        for src, tgt in zip(names, names[1:], strict=False)
    ]
    if edges:
        result["edges"] = edges
        logger.info("AI 未产出关系，已按目录补全 %d 条关系边", len(edges))


class ExtractionService:
    def __init__(
        self,
        ai_service: AIService,
        graph_service: GraphService,
        max_attempts: int | None = None,
        backoff_seconds: float | None = None,
        session_factory=None,
    ):
        self.ai_service = ai_service
        self.graph_service = graph_service
        self.session_factory = session_factory
        self.max_attempts = max_attempts or settings.EXTRACTION_MAX_ATTEMPTS
        self.backoff_seconds = (
            backoff_seconds
            if backoff_seconds is not None
            else settings.EXTRACTION_BACKOFF_SECONDS
        )

    async def _update_note(self, note_id: str, **fields) -> None:
        """尽力回写笔记抽取状态，失败不影响主流程。"""
        if self.session_factory is None:
            return
        try:
            from sqlalchemy import update

            from app.models.note import Note

            async with self.session_factory() as session:
                await session.execute(
                    update(Note).where(Note.id == note_id).values(**fields)
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("回写笔记状态失败 note_id=%s error=%s", note_id, exc)

    async def _grow_pet(self, user_id: str, nodes_count: int) -> None:
        """知识输入驱动宠物花园的树木/果实成长，失败不影响主流程。"""
        if self.session_factory is None or nodes_count <= 0:
            return
        try:
            from app.services import pet_service

            async with self.session_factory() as session:
                await pet_service.apply_knowledge_growth(session, user_id, nodes_count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识驱动成长失败 user_id=%s error=%s", user_id, exc)

    async def extract_and_build_graph(
        self, note_id: str, user_id: str, file_path: str, fmt: str
    ) -> dict:
        await self._update_note(note_id, status=NOTE_STATUS["PROCESSING"], error_message=None)

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = await self._extract_once(
                    note_id, user_id, file_path, fmt, attempt
                )
                status = result.get("status", NOTE_STATUS["SUCCESS"])
                if status == NOTE_STATUS["EMPTY"]:
                    await self._update_note(
                        note_id,
                        status=NOTE_STATUS["EMPTY"],
                        nodes_count=0,
                        edges_count=0,
                        processed_time=datetime.now(timezone.utc),
                    )
                else:
                    nodes_count = result.get("nodes_count", len(result.get("nodes", [])))
                    edges_count = result.get("edges_count", len(result.get("edges", [])))
                    await self._update_note(
                        note_id,
                        status=NOTE_STATUS["SUCCESS"],
                        nodes_count=nodes_count,
                        edges_count=edges_count,
                        processed_time=datetime.now(timezone.utc),
                    )
                    await self._grow_pet(user_id, nodes_count)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "知识抽取失败 attempt=%d/%d note_id=%s user_id=%s error=%s",
                    attempt,
                    self.max_attempts,
                    note_id,
                    user_id,
                    exc,
                )
                if attempt < self.max_attempts:
                    delay = self.backoff_seconds * (2 ** (attempt - 1))
                    logger.info("将在 %.1f 秒后重试 note_id=%s", delay, note_id)
                    await asyncio.sleep(delay)

        logger.error(
            "知识抽取最终失败 note_id=%s user_id=%s attempts=%d error=%s",
            note_id,
            user_id,
            self.max_attempts,
            last_error,
            exc_info=last_error,
        )
        await self._update_note(
            note_id,
            status=NOTE_STATUS["FAILED"],
            error_message=str(last_error),
            processed_time=datetime.now(timezone.utc),
        )
        return {
            "nodes": [],
            "edges": [],
            "status": NOTE_STATUS["FAILED"],
            "error": str(last_error),
        }

    async def _load_image_text(self, note_id: str) -> str:
        """图片正文来自上传时同步 OCR 的结果，直接读取以免重复识别。"""
        if self.session_factory is None:
            return ""
        try:
            from sqlalchemy import select

            from app.models.note import Note

            async with self.session_factory() as session:
                res = await session.execute(
                    select(Note.content).where(Note.id == note_id)
                )
                return res.scalar_one_or_none() or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取图片笔记正文失败 note_id=%s error=%s", note_id, exc)
            return ""

    async def _extract_once(
        self, note_id: str, user_id: str, file_path: str, fmt: str, attempt: int
    ) -> dict:
        logger.info("开始知识抽取 note_id=%s attempt=%d", note_id, attempt)
        # 注意：上传侧传入的 fmt 不带点（"png"），而 IMAGE_EXTENSIONS 是带点的（".png"），
        # 直接 `fmt in IMAGE_EXTENSIONS` 恒为 False，会把图片笔记误送进 parse_file 并报
        # 「不支持的文件格式」。这里统一补点后再比较。
        if f".{fmt.lstrip('.')}" in settings.IMAGE_EXTENSIONS:
            text = await self._load_image_text(note_id)
        else:
            text = parse_file(file_path, fmt)
        if not text or not text.strip():
            logger.warning("文件内容为空，跳过知识抽取 note_id=%s", note_id)
            return {"nodes": [], "edges": [], "status": NOTE_STATUS["EMPTY"]}

        result = await self.ai_service.extract_knowledge(text)
        if result.get("status") == "failed":
            raise RuntimeError(result.get("message") or "AI 服务不可用")

        if not (result.get("categories") or result.get("nodes")):
            logger.warning(
                "LLM 未返回任何知识点，标记为空可重试 note_id=%s", note_id
            )
            return {"nodes": [], "edges": [], "status": NOTE_STATUS["EMPTY"]}

        book_title = ""
        if self.session_factory is not None:
            try:
                from sqlalchemy import select

                from app.models.note import Note

                async with self.session_factory() as session:
                    res = await session.execute(
                        select(Note.title).where(Note.id == note_id)
                    )
                    row = res.scalar_one_or_none()
                    if row:
                        book_title = row
            except Exception:
                pass

        _backfill_edges(result)

        await self.graph_service.write_extraction_result(
            user_id=user_id, note_id=note_id, result=result, book_title=book_title
        )

        categories = result.get("categories", [])

        def _count_category(c: dict) -> int:
            return 1 + sum(_count_category(s) for s in c.get("categories", [])) + len(c.get("knowledge_points", []))

        if categories:
            total_nodes = 1 + sum(_count_category(c) for c in categories)
        else:
            # legacy 扁平结构：book 根节点 + 每个知识节点（与 graph_service 落库逻辑一致）
            total_nodes = 1 + len(result.get("nodes", []))
        edge_count = len(result.get("edges", []))
        logger.info(
            "知识抽取完成 note_id=%s total_nodes=%d edges=%d",
            note_id, total_nodes, edge_count,
        )
        return {**result, "status": NOTE_STATUS["SUCCESS"], "nodes_count": total_nodes, "edges_count": edge_count}
