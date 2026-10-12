import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_WELCOME_MESSAGE, settings
from app.core.logger import get_logger
from app.models.avatar import Avatar, ChatMessage
from app.models.note import Note
from app.models.reflection import ReflectionRecord
from app.services.ai_service import AIService
from app.services.graph_service import GraphService
from app.services.providers.base import AI_BUSY_MESSAGE, LLM_ERROR_TYPES

logger = get_logger(__name__)


BLOCK_MESSAGE = "抱歉，该问题超出我的知识范围"
ANONYMOUS_VISITOR = "anonymous"


def _visitor_display_name(visitor_key: str) -> str:
    # 访客标识是服务端生成的随机串，对用户没有意义，统一显示为「访客」，
    # 具体来访者通过列表中的提问摘要区分
    if visitor_key == ANONYMOUS_VISITOR:
        return "匿名访客"
    return "访客"


class AvatarService:
    def __init__(
        self,
        db: AsyncSession,
        ai_service: AIService,
        graph_service: GraphService,
    ):
        self.db = db
        self.ai_service = ai_service
        self.graph_service = graph_service

    async def generate_profile(self, user_id: str) -> dict:
        distribution = await self.graph_service.get_subject_distribution(user_id)
        overview = await self.graph_service.get_mastery_overview(user_id)

        result = await self.db.execute(
            select(ReflectionRecord).where(ReflectionRecord.user_id == user_id)
        )
        reflections = list(result.scalars().all())
        answered = [r for r in reflections if r.mastery_score is not None]

        avg_score = 0.0
        if answered:
            avg_score = sum(r.mastery_score for r in answered) / len(answered)

        dimensions = {
            "概念准确性": [r.concept_accuracy for r in answered if r.concept_accuracy is not None],
            "逻辑完整性": [r.logic_completeness for r in answered if r.logic_completeness is not None],
            "举例合理性": [r.example_reasonableness for r in answered if r.example_reasonableness is not None],
        }
        dimension_avg = {}
        for name, values in dimensions.items():
            dimension_avg[name] = round(sum(values) / len(values), 1) if values else 0.0

        strongest = None
        weakest = None
        if any(dimension_avg.values()):
            strongest = max(dimension_avg, key=dimension_avg.get)
            weakest = min(dimension_avg, key=dimension_avg.get)

        reflection_style = {
            "total_reflections": len(reflections),
            "answered": len(answered),
            "completion_rate": round(len(answered) / len(reflections), 2) if reflections else 0.0,
            "avg_score": round(avg_score, 1),
            "dimension_averages": dimension_avg,
            "strongest_dimension": strongest,
            "weakest_dimension": weakest,
        }

        summary = (
            f"共 {overview.get('total', 0)} 个知识点，覆盖 {len(distribution)} 个学科，"
            f"平均掌握度 {overview.get('avg_mastery', 0.0):.1f}；"
            f"已完成 {len(answered)} 次反思，平均得分 {avg_score:.1f}。"
        )

        return {
            "domain_distribution": distribution,
            "mastery_overview": overview,
            "reflection_style": reflection_style,
            "summary": summary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_avatar_for_user(self, user_id: str) -> Avatar | None:
        result = await self.db.execute(select(Avatar).where(Avatar.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_avatar_id(self, avatar_id: str) -> Avatar | None:
        result = await self.db.execute(
            select(Avatar).where(
                (Avatar.id == avatar_id) | (Avatar.share_token == avatar_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_avatar(self, user_id: str) -> Avatar:
        avatar = await self.get_avatar_for_user(user_id)
        if avatar is None:
            avatar = Avatar(
                user_id=user_id,
                share_token=secrets.token_urlsafe(16),
                knowledge_scope=[],
            )
            self.db.add(avatar)
            await self.db.commit()
            await self.db.refresh(avatar)
        return avatar

    def _apply_config(self, avatar: Avatar, config: dict) -> None:
        if config.get("tone"):
            avatar.tone = config["tone"]
        if config.get("welcome_message") is not None:
            avatar.welcome_message = config["welcome_message"] or DEFAULT_WELCOME_MESSAGE
        if config.get("knowledge_scope") is not None:
            avatar.knowledge_scope = list(config["knowledge_scope"])
        if config.get("avatar_url") is not None:
            avatar.avatar_url = config["avatar_url"] or None

    async def update_config(self, user_id: str, config: dict) -> Avatar:
        avatar = await self.get_or_create_avatar(user_id)
        self._apply_config(avatar, config)
        await self.db.commit()
        await self.db.refresh(avatar)
        return avatar

    async def publish(self, user_id: str, config: dict | None = None) -> Avatar:
        avatar = await self.get_or_create_avatar(user_id)
        if config:
            self._apply_config(avatar, config)
        avatar.profile = await self.generate_profile(user_id)
        if not avatar.share_token:
            avatar.share_token = secrets.token_urlsafe(16)
        avatar.status = "online"
        await self.db.commit()
        await self.db.refresh(avatar)
        await self._backfill_embeddings(user_id)
        return avatar

    async def unpublish(self, user_id: str) -> Avatar:
        avatar = await self.get_or_create_avatar(user_id)
        avatar.status = "offline"
        await self.db.commit()
        await self.db.refresh(avatar)
        return avatar

    def build_share_url(self, avatar: Avatar) -> str:
        return f"{settings.SHARE_BASE_URL}/chat/{avatar.id}"

    async def resolve_knowledge_scope(self, avatar: Avatar) -> list[str]:
        """把 knowledge_scope 中的知识书 id 解析为书名（历史数据存过 id）。"""
        scope = avatar.knowledge_scope or []
        if not scope:
            return []
        try:
            books = await self.graph_service.get_books(avatar.user_id)
        except Exception:  # noqa: BLE001
            return list(scope)
        id_to_name = {b.get("id"): b.get("name") for b in books}
        return [id_to_name.get(item, item) for item in scope]

    async def _backfill_embeddings(self, user_id: str) -> None:
        try:

            nodes = await self.graph_service.get_nodes_without_embedding(
                user_id, limit=settings.AVATAR_EMBED_BACKFILL_LIMIT
            )
        except Exception:
            logger.exception("查询待向量化节点失败")
            return
        for node in nodes:
            text = f"{node.get('name', '')} {node.get('summary', '')}".strip()
            if not text:
                continue
            try:
                embedding = await self.ai_service.embed(text)
            except Exception:
                logger.exception("节点向量化失败 node_id=%s", node.get("id"))
                break
            try:
                await self.graph_service.set_node_embedding(
                    user_id, node["id"], embedding
                )
            except Exception:
                logger.exception("写入节点向量失败 node_id=%s", node.get("id"))

    async def rag_search(
        self, user_id: str, query: str, top_k: int | None = None
    ) -> list[dict]:
        top_k = top_k or settings.AVATAR_TOP_K
        if getattr(self.ai_service, "embedding", None) is None:
            return []
        try:
            query_embedding = await self.ai_service.embed(query)
        except Exception:
            logger.exception("查询 Embedding 失败")
            return []
        try:
            hits = await self.graph_service.vector_search(
                user_id,
                query_embedding,
                top_k=top_k,
                index_name=settings.NEO4J_VECTOR_INDEX,
            )
        except Exception:
            logger.exception("Neo4j 向量检索失败")
            return []
        return hits

    async def _build_sources_and_context(
        self, hits: list[dict]
    ) -> tuple[list[dict], str]:
        note_ids = [
            h["node"].get("source_note_id")
            for h in hits
            if h["node"].get("source_note_id")
        ]
        titles: dict[str, str] = {}
        if note_ids:
            rows = await self.db.execute(
                select(Note.id, Note.title).where(Note.id.in_(note_ids))
            )
            for note_id, title in rows.all():
                titles[note_id] = title

        sources = []
        lines = []
        for hit in hits:
            node = hit["node"]
            note_title = titles.get(node.get("source_note_id"))
            sources.append({
                "node_id": node.get("id"),
                "name": node.get("name", ""),
                "summary": node.get("summary", ""),
                "subject": node.get("subject"),
                "mastery": node.get("mastery", 0.0),
                "score": hit.get("score", 0.0),
                "source_note_id": node.get("source_note_id"),
                "note_title": note_title,
            })
            line = (
                f"- 知识点：{node.get('name', '')}"
                f"（{node.get('subject') or '未分类'}）；"
                f"摘要：{node.get('summary') or '无'}；"
                f"掌握度：{node.get('mastery', 0.0)}"
            )
            if note_title:
                line += f"；来源笔记：《{note_title}》"
            lines.append(line)
        return sources, "\n".join(lines)

    async def _save_message(
        self,
        avatar_id: str,
        visitor_id: str | None,
        role: str,
        content: str,
        sources: list | None,
    ) -> None:
        message = ChatMessage(
            avatar_id=avatar_id,
            visitor_id=visitor_id,
            role=role,
            content=content,
            sources=sources,
        )
        self.db.add(message)
        await self.db.commit()

    _SMALLTALK_PATTERNS = (
        "你好", "您好", "hi", "hello", "嗨", "哈喽", "在吗", "在么", "在不在",
        "在干嘛", "在干什么", "干嘛呢", "忙吗", "忙不忙",
        "你是谁", "你叫什么", "你是什么", "你能做什么", "你会什么",
        "你能干什么", "介绍一下你", "自我介绍", "你是干什么的",
        "谢谢", "多谢", "感谢", "thanks", "thank you",
        "再见", "拜拜", "bye", "晚安", "早安", "早上好", "中午好",
        "下午好", "晚上好", "好的", "收到",
    )

    @classmethod
    def _is_smalltalk(cls, query: str) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False
        cleaned = "".join(
            ch for ch in text
            if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"
        )
        if not cleaned or len(cleaned) > 15:
            return False
        for pattern in cls._SMALLTALK_PATTERNS:
            if cleaned.startswith(pattern) and len(cleaned) - len(pattern) <= 2:
                return True
        return False

    async def stream_answer(
        self,
        avatar: Avatar,
        query: str,
        history: list[dict] | None = None,
        visitor_id: str | None = None,
    ):
        history = history or []

        if self._is_smalltalk(query):
            await self._save_message(avatar.id, visitor_id, "user", query, None)
            chunks: list[str] = []
            try:
                async for token in self.ai_service.avatar_smalltalk_stream(
                    query=query, tone=avatar.tone, history=history
                ):
                    chunks.append(token)
                    yield {"type": "chunk", "content": token}
            except LLM_ERROR_TYPES as exc:
                logger.warning("分身闲聊调用 LLM 失败，触发降级：%s", exc)
                yield {"type": "error", "message": AI_BUSY_MESSAGE, "sources": []}
                return
            answer = "".join(chunks)
            await self._save_message(avatar.id, visitor_id, "assistant", answer, [])
            yield {"type": "done", "answer": answer}
            return

        # 同时尝试向量语义检索与关键词检索：任一来源达标即可作答，取分高者。
        # 避免"向量低分命中却堵死关键词兜底"导致的错误拒答。
        vector_hits = await self.rag_search(avatar.user_id, query)
        keyword_hits = await self.graph_service.keyword_search(
            avatar.user_id, query, top_k=settings.AVATAR_TOP_K
        )

        vector_score = vector_hits[0]["score"] if vector_hits else 0.0
        keyword_score = keyword_hits[0]["score"] if keyword_hits else 0.0

        hits: list[dict] = []
        accepted_score = 0.0
        if vector_hits and vector_score >= settings.AVATAR_SIMILARITY_THRESHOLD:
            hits, accepted_score = vector_hits, vector_score
        if (
            keyword_hits
            and keyword_score >= settings.AVATAR_KEYWORD_THRESHOLD
            and keyword_score > accepted_score
        ):
            hits, accepted_score = keyword_hits, keyword_score

        await self._save_message(avatar.id, visitor_id, "user", query, None)

        if not hits:
            yield {"type": "blocked", "message": BLOCK_MESSAGE, "sources": []}
            await self._save_message(
                avatar.id, visitor_id, "assistant", BLOCK_MESSAGE, []
            )
            return

        sources, context = await self._build_sources_and_context(hits)
        yield {"type": "sources", "sources": sources}

        chunks = []
        try:
            async for token in self.ai_service.avatar_chat_stream(
                query=query,
                context=context,
                tone=avatar.tone,
                history=history,
            ):
                chunks.append(token)
                yield {"type": "chunk", "content": token}
        except LLM_ERROR_TYPES as exc:
            logger.warning("分身对话调用 LLM 失败，触发降级：%s", exc)
            yield {"type": "error", "message": AI_BUSY_MESSAGE, "sources": sources}
            return

        answer = "".join(chunks)
        await self._save_message(avatar.id, visitor_id, "assistant", answer, sources)
        yield {"type": "done", "answer": answer}

    async def get_stats(self, user_id: str, avatar_id: str) -> dict | None:
        avatar = await self.get_by_avatar_id(avatar_id)
        if avatar is None or avatar.user_id != user_id:
            return None

        visitor_key = func.coalesce(ChatMessage.visitor_id, "anonymous")

        total_conversations = await self.db.scalar(
            select(func.count(func.distinct(visitor_key))).where(
                ChatMessage.avatar_id == avatar.id,
                ChatMessage.role == "user",
            )
        )
        total_messages = await self.db.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.avatar_id == avatar.id
            )
        )
        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        today_conversations = await self.db.scalar(
            select(func.count(func.distinct(visitor_key))).where(
                ChatMessage.avatar_id == avatar.id,
                ChatMessage.role == "user",
                ChatMessage.created_at >= start_of_day,
            )
        )
        top_rows = await self.db.execute(
            select(ChatMessage.content, func.count(ChatMessage.id).label("cnt"))
            .where(
                ChatMessage.avatar_id == avatar.id,
                ChatMessage.role == "user",
            )
            .group_by(ChatMessage.content)
            .order_by(func.count(ChatMessage.id).desc())
            .limit(5)
        )
        top_questions = [
            {"question": content, "count": cnt} for content, cnt in top_rows.all()
        ]

        return {
            "total_conversations": total_conversations or 0,
            "today_conversations": today_conversations or 0,
            "total_messages": total_messages or 0,
            "top_questions": top_questions,
        }
    async def get_conversations(
        self, user_id: str, avatar_id: str, limit: int | None = None
    ) -> list[dict] | None:
        avatar = await self.get_by_avatar_id(avatar_id)
        if avatar is None or avatar.user_id != user_id:
            return None

        visitor_key = func.coalesce(ChatMessage.visitor_id, ANONYMOUS_VISITOR)
        query = (
            select(
                visitor_key.label("visitor"),
                func.count(ChatMessage.id).label("message_count"),
                func.max(ChatMessage.created_at).label("last_message_at"),
            )
            .where(ChatMessage.avatar_id == avatar.id)
            .group_by(visitor_key)
            .order_by(func.max(ChatMessage.created_at).desc())
        )
        if limit is not None:
            query = query.limit(limit)
        rows = await self.db.execute(query)
        base_rows = rows.all()

        # 访客提问数与最后一次提问一次性取回，避免逐访客 N+1 查询
        question_count: dict[str, int] = {}
        last_question: dict[str, str | None] = {}
        q_rows = await self.db.execute(
            select(
                visitor_key.label("visitor"),
                ChatMessage.content,
                ChatMessage.created_at,
            )
            .where(
                ChatMessage.avatar_id == avatar.id,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.created_at.desc())
        )
        for visitor, content, _created in q_rows.all():
            question_count[visitor] = question_count.get(visitor, 0) + 1
            if visitor not in last_question:
                last_question[visitor] = content

        summaries: list[dict] = []
        for visitor, message_count, last_message_at in base_rows:
            summaries.append(
                {
                    "visitor_id": visitor,
                    "display_name": _visitor_display_name(visitor),
                    "message_count": message_count or 0,
                    "question_count": question_count.get(visitor, 0),
                    "last_message_at": last_message_at,
                    "last_question": last_question.get(visitor),
                }
            )
        return summaries

    async def get_conversation(
        self, user_id: str, avatar_id: str, visitor_id: str
    ) -> dict | None:
        avatar = await self.get_by_avatar_id(avatar_id)
        if avatar is None or avatar.user_id != user_id:
            return None

        visitor_key = func.coalesce(ChatMessage.visitor_id, ANONYMOUS_VISITOR)
        result = await self.db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.avatar_id == avatar.id,
                visitor_key == visitor_id,
            )
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        messages = [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "sources": m.sources or [],
            }
            for m in result.scalars().all()
        ]
        return {
            "visitor_id": visitor_id,
            "display_name": _visitor_display_name(visitor_id),
            "messages": messages,
        }
