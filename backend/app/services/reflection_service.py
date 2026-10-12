import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.reflection import ReflectionRecord, ReflectionSchedule
from app.services.ai_service import AIService
from app.services.graph_service import GraphService
from app.services.providers.base import AI_BUSY_MESSAGE

logger = get_logger(__name__)

# 同一题目的并发提交串行化：SQLite 不支持 SELECT ... FOR UPDATE（见下方注释），
# 单进程部署下用进程内锁兜底，避免同一份答案被评估多次、拿到多个不同分数。
_ANSWER_LOCKS: dict[str, asyncio.Lock] = {}
_ANSWER_LOCKS_MAX = 512


def _answer_lock(user_id: str, question_id: str) -> asyncio.Lock:
    key = f"{user_id}:{question_id}"
    lock = _ANSWER_LOCKS.get(key)
    if lock is None:
        if len(_ANSWER_LOCKS) >= _ANSWER_LOCKS_MAX:
            for stale_key in [k for k, v in _ANSWER_LOCKS.items() if not v.locked()]:
                _ANSWER_LOCKS.pop(stale_key, None)
        lock = asyncio.Lock()
        _ANSWER_LOCKS[key] = lock
    return lock


MASTERY_THRESHOLD = 60.0
DAYS_THRESHOLD = 7
MAX_QUESTIONS = 5

WEIGHT_CONCEPT = 0.4
WEIGHT_LOGIC = 0.35
WEIGHT_EXAMPLE = 0.25

MASTERY_OLD_WEIGHT = 0.4
MASTERY_NEW_WEIGHT = 0.6
# 时间衰减：距上次复习越久，旧掌握度越不可信，新观测权重越大（半衰期 14 天）
MASTERY_DECAY_HALFLIFE_DAYS = 14.0
# 动态融合时新观测权重上限（避免旧掌握度被一次性覆盖）
MASTERY_MAX_NEW_WEIGHT = 0.85


def _days_since(last_reviewed) -> float | None:
    """把图谱节点上的 last_reviewed 时间转换为距今的天数；缺失或非法时返回 None。"""
    if last_reviewed is None:
        return None
    try:
        if hasattr(last_reviewed, "to_native"):
            last_reviewed = last_reviewed.to_native()
        if last_reviewed.tzinfo is None:
            last_reviewed = last_reviewed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last_reviewed
        return max(0.0, delta.total_seconds() / 86400.0)
    except (AttributeError, TypeError, ValueError):
        return None


def compute_mastery_weights(
    old_mastery: float, days_since_review: float | None
) -> tuple[float, float]:
    """按遗忘（时间）与难度动态调整新旧掌握度的融合权重。

    - 时间因子：越久未复习，旧掌握度越不可信，新观测权重越大（半衰期 14 天）；
    - 难度因子：当前掌握度越低，说明该知识点对该用户越难，单次作答应更快更新。
    返回 (old_weight, new_weight)，两者之和恒为 1。
    """
    if days_since_review is None or days_since_review <= 0:
        time_factor = 0.0
    else:
        time_factor = 1.0 - 0.5 ** (days_since_review / MASTERY_DECAY_HALFLIFE_DAYS)

    difficulty_factor = max(0.0, min(1.0, 1.0 - old_mastery / 100.0))

    # 取两因子的「并集」，任一显著即加大新权重，同时避免叠加越界
    factor = 1.0 - (1.0 - time_factor) * (1.0 - difficulty_factor)
    new_weight = MASTERY_NEW_WEIGHT + (MASTERY_MAX_NEW_WEIGHT - MASTERY_NEW_WEIGHT) * factor
    new_weight = min(MASTERY_MAX_NEW_WEIGHT, max(MASTERY_NEW_WEIGHT, new_weight))
    return 1.0 - new_weight, new_weight


class ReflectionService:
    def __init__(
        self,
        db: AsyncSession,
        ai_service: AIService,
        graph_service: GraphService,
    ):
        self.db = db
        self.ai_service = ai_service
        self.graph_service = graph_service

    async def generate_questions(
        self, user_id: str, max_questions: int = MAX_QUESTIONS
    ) -> list[ReflectionRecord]:
        nodes = await self.graph_service.get_nodes_for_review(
            user_id=user_id,
            mastery_threshold=MASTERY_THRESHOLD,
            days_threshold=DAYS_THRESHOLD,
            limit=max_questions,
        )

        records = []
        for node in nodes:
            node_id = node.get("id")
            node_name = node.get("name", "未知知识点")
            node_summary = node.get("summary", "")

            try:
                question_text = await self.ai_service.generate_question(
                    node_name=node_name,
                    node_summary=node_summary,
                )
            except Exception:
                logger.exception("生成问题失败: node_id=%s", node_id)
                continue

            record = ReflectionRecord(
                user_id=user_id,
                question=question_text,
                target_node_id=node_id,
                node_name=node_name,
            )
            self.db.add(record)
            records.append(record)

        await self.db.commit()
        for record in records:
            await self.db.refresh(record)

        return records

    async def get_today_questions(self, user_id: str) -> list[ReflectionRecord]:
        today_start = datetime.now(timezone.utc).replace(
            tzinfo=None, hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_start = today_start + timedelta(days=1)

        result = await self.db.execute(
            select(ReflectionRecord)
            .where(
                ReflectionRecord.user_id == user_id,
                ReflectionRecord.created_at >= today_start,
                ReflectionRecord.created_at < tomorrow_start,
                ReflectionRecord.answer.is_(None),
            )
            .order_by(ReflectionRecord.created_at.desc(), ReflectionRecord.id.desc())
        )
        return list(result.scalars().all())

    async def evaluate_answer(
        self, user_id: str, question_id: str, answer: str, is_voice: bool = False
    ) -> dict:
        # with_for_update() 在 SQLite 下是 no-op，因此这里再用进程内锁串行化同一题目，
        # 保证并发重复提交只会评估一次，后续请求直接返回已保存的结果。
        async with _answer_lock(user_id, question_id):
            return await self._evaluate_answer_locked(
                user_id=user_id,
                question_id=question_id,
                answer=answer,
                is_voice=is_voice,
            )

    async def _evaluate_answer_locked(
        self, user_id: str, question_id: str, answer: str, is_voice: bool = False
    ) -> dict:
        result = await self.db.execute(
            select(ReflectionRecord)
            .where(
                ReflectionRecord.id == question_id,
                ReflectionRecord.user_id == user_id,
            )
            # 行级锁串行化同一题的并发提交，避免两次都通过 answer is None
            # 判定而重复打分/重复更新掌握度（SQLite 下为 no-op，Postgres 生效）
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        if record.answer is not None:
            return {
                "mastery_score": record.mastery_score or 0.0,
                "concept_accuracy": record.concept_accuracy or 0.0,
                "logic_completeness": record.logic_completeness or 0.0,
                "example_reasonableness": record.example_reasonableness or 0.0,
                "weak_points": [],
                "suggestion": record.feedback or "",
                "resources": [],
            }

        evaluation = await self.ai_service.evaluate_answer(
            node_name=record.node_name or "",
            question=record.question,
            answer=answer,
        )
        if evaluation.get("status") == "failed":
            return {
                "status": "failed",
                "message": evaluation.get("message") or AI_BUSY_MESSAGE,
            }

        concept = float(evaluation.get("concept_accuracy", 0.0))
        logic = float(evaluation.get("logic_completeness", 0.0))
        example = float(evaluation.get("example_reasonableness", 0.0))

        weighted_score = (
            concept * WEIGHT_CONCEPT
            + logic * WEIGHT_LOGIC
            + example * WEIGHT_EXAMPLE
        )

        record.answer = answer
        record.is_voice = is_voice
        record.feedback = evaluation.get("suggestion", "")
        record.mastery_score = weighted_score
        record.concept_accuracy = concept
        record.logic_completeness = logic
        record.example_reasonableness = example
        record.answered_at = datetime.now(timezone.utc).replace(tzinfo=None)

        old_mastery = 0.0
        if record.target_node_id:
            node = await self.graph_service.get_node_detail(
                user_id=user_id, node_id=record.target_node_id
            )
            if node:
                old_mastery = float(node.get("mastery", 0.0))

            days_since_review = _days_since(node.get("last_reviewed")) if node else None
            old_weight, new_weight = compute_mastery_weights(old_mastery, days_since_review)
            new_mastery = old_mastery * old_weight + weighted_score * new_weight
            await self.graph_service.update_mastery(
                user_id=user_id,
                node_id=record.target_node_id,
                mastery=new_mastery,
            )

        await self.db.commit()
        await self.db.refresh(record)

        return {
            "mastery_score": weighted_score,
            "concept_accuracy": concept,
            "logic_completeness": logic,
            "example_reasonableness": example,
            "weak_points": evaluation.get("weak_points", []),
            "suggestion": evaluation.get("suggestion", ""),
            "resources": evaluation.get("resources", []),
        }

    async def get_history(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> dict:
        count_result = await self.db.execute(
            select(sql_func.count(ReflectionRecord.id)).where(
                ReflectionRecord.user_id == user_id
            )
        )
        total = count_result.scalar() or 0

        result = await self.db.execute(
            select(ReflectionRecord)
            .where(ReflectionRecord.user_id == user_id)
            .order_by(ReflectionRecord.created_at.desc(), ReflectionRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(result.scalars().all())

        return {"items": items, "total": total}

    async def get_mastery_trend(self, user_id: str) -> dict:
        result = await self.db.execute(
            select(ReflectionRecord)
            .where(
                ReflectionRecord.user_id == user_id,
                ReflectionRecord.target_node_id.is_not(None),
                ReflectionRecord.mastery_score.is_not(None),
            )
            .order_by(ReflectionRecord.created_at.asc())
        )
        records = list(result.scalars().all())

        node_map: dict[str, dict] = {}
        timeline = []
        for record in records:
            node_id = record.target_node_id
            entry = node_map.get(node_id)
            if entry is None:
                entry = {
                    "node_id": node_id,
                    "node_name": record.node_name or "",
                    "mastery": 0.0,
                    "history": [],
                    "_last_time": None,
                }
                node_map[node_id] = entry

            # 与图谱侧口径统一：节点掌握度按同一 EMA（含时间/难度权重）顺序融合，
            # 而非直接取最近一次会话分，避免「趋势」与「图谱节点」两个数字对不上。
            score = record.mastery_score or 0.0
            days = None
            if entry["_last_time"] is not None and record.answered_at is not None:
                days = max(
                    0.0,
                    (record.answered_at - entry["_last_time"]).total_seconds() / 86400.0,
                )
            old_weight, new_weight = compute_mastery_weights(entry["mastery"], days)
            entry["mastery"] = entry["mastery"] * old_weight + score * new_weight

            entry["history"].append({
                "time": record.answered_at.isoformat() if record.answered_at else None,
                "score": record.mastery_score,
            })
            if record.answered_at is not None:
                entry["_last_time"] = record.answered_at
            timeline.append({
                "time": record.answered_at.isoformat() if record.answered_at else None,
                "node_id": node_id,
                "node_name": record.node_name or "",
                "score": record.mastery_score,
            })

        for entry in node_map.values():
            entry.pop("_last_time", None)

        return {"nodes": list(node_map.values()), "timeline": timeline}

    async def get_schedule(self, user_id: str) -> ReflectionSchedule:
        result = await self.db.execute(
            select(ReflectionSchedule).where(
                ReflectionSchedule.user_id == user_id
            )
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            schedule = ReflectionSchedule(user_id=user_id)
            self.db.add(schedule)
            await self.db.commit()
            await self.db.refresh(schedule)
        return schedule

    async def update_schedule(
        self, user_id: str, frequency: str, time_window: str
    ) -> ReflectionSchedule:
        result = await self.db.execute(
            select(ReflectionSchedule).where(
                ReflectionSchedule.user_id == user_id
            )
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            schedule = ReflectionSchedule(
                user_id=user_id,
                frequency=frequency,
                time_window=time_window,
            )
            self.db.add(schedule)
        else:
            schedule.frequency = frequency
            schedule.time_window = time_window

        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule
