import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.reflection import ReflectionRecord, ReflectionSchedule
from app.services import review_signals
from app.services.ai_service import AIService
from app.services.graph_service import GraphService
from app.services.providers.base import AI_BUSY_MESSAGE

logger = get_logger(__name__)


def _to_score(value, default: float = 0.0) -> float:
    """把 AI 返回的评分安全转成 float：85→85.0, '85分'→85.0, None→0.0, '优'→0.0"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        m = re.search(r"\d+(?:\.\d+)?", str(value))
        return float(m.group()) if m else default


def _dump_list(value) -> str | None:
    """把评分返回的列表存成 JSON 字符串；空值存 NULL，避免库里出现 "[]" 噪声。"""
    if not value:
        return None
    if isinstance(value, str):
        value = [value]
    return json.dumps(list(value), ensure_ascii=False)


def _load_list(value) -> list[str]:
    """读取弱项/资源：兼容历史数据里可能是纯文本或非法 JSON 的情况。"""
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [value]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [str(parsed)]


def _iso_utc(dt: datetime | None) -> str | None:
    """naive datetime 一律按 UTC 解释，输出带 Z 的 ISO 串。

    直接 `.isoformat()` 会得到 "2026-11-05T03:56:31"（没有时区），
    浏览器 `new Date(...)` 会把它当本地时间，溯源时间线整体偏 8 小时。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _local_day_bounds() -> tuple[datetime, datetime]:
    """按 settings.TIMEZONE_OFFSET_HOURS 切本地日界，返回 [今日0点, 明日0点) 的 naive UTC datetime。"""
    now_utc = datetime.now(timezone.utc)
    local_now = now_utc + timedelta(hours=settings.TIMEZONE_OFFSET_HOURS)
    local_today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_tomorrow_start = local_today_start + timedelta(days=1)
    return local_today_start - timedelta(hours=settings.TIMEZONE_OFFSET_HOURS), local_tomorrow_start - timedelta(hours=settings.TIMEZONE_OFFSET_HOURS)

# 同一题目的并发提交串行化：SQLite 不支持 SELECT ... FOR UPDATE（见下方注释），
# 单进程部署下用进程内锁兜底，避免同一份答案被评估多次、拿到多个不同分数。
#
# 键是 (事件循环 id, 业务键)：asyncio.Lock 绑定创建它的循环，跨循环复用会直接抛
# 「bound to a different event loop」。缓存若不区分循环，进程内重启循环（测试、
# 重载、部分 ASGI 服务器）后第一次加锁就炸。
_ANSWER_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_ANSWER_LOCKS_MAX = 512
_GENERATE_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_GENERATE_LOCKS_MAX = 256
# 掌握度是「读旧值 → 加权 → 写回」，同一知识点被两道题并发评分时会丢更新。
# 题目级锁管不到这种情况（题不同、节点相同），所以再按 (user, node) 加一把。
_MASTERY_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_MASTERY_LOCKS_MAX = 1024


def _get_lock(
    cache: dict[tuple[int, str], asyncio.Lock], max_size: int, key: str
) -> asyncio.Lock:
    loop_id = id(asyncio.get_running_loop())
    cache_key = (loop_id, key)
    lock = cache.get(cache_key)
    if lock is not None:
        return lock

    if len(cache) >= max_size:
        # 先清掉别的（已结束的）循环遗留的锁，再清当前循环里空闲的锁
        for stale in [k for k in cache if k[0] != loop_id]:
            cache.pop(stale, None)
        if len(cache) >= max_size:
            for stale, value in list(cache.items()):
                if not value.locked():
                    cache.pop(stale, None)

    lock = asyncio.Lock()
    cache[cache_key] = lock
    return lock


def _mastery_lock(user_id: str, node_id: str) -> asyncio.Lock:
    return _get_lock(_MASTERY_LOCKS, _MASTERY_LOCKS_MAX, f"{user_id}:{node_id}")


def _answer_lock(user_id: str, question_id: str) -> asyncio.Lock:
    return _get_lock(_ANSWER_LOCKS, _ANSWER_LOCKS_MAX, f"{user_id}:{question_id}")


def _generate_lock(user_id: str) -> asyncio.Lock:
    return _get_lock(_GENERATE_LOCKS, _GENERATE_LOCKS_MAX, user_id)


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
    """把图谱节点上的 last_reviewed 时间转换为距今的天数；缺失或非法时返回 None。

    演示图谱（只读 JSONL）里的时间是 ISO 字符串，Neo4j 里是 DateTime，
    两种都要认——否则演示环境的「越久没复习权重越大」永远不生效。
    """
    if last_reviewed is None:
        return None
    try:
        if isinstance(last_reviewed, str):
            last_reviewed = datetime.fromisoformat(last_reviewed.replace("Z", "+00:00"))
        elif hasattr(last_reviewed, "to_native"):
            last_reviewed = last_reviewed.to_native()
        if last_reviewed.tzinfo is None:
            last_reviewed = last_reviewed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last_reviewed
        return max(0.0, delta.total_seconds() / 86400.0)
    except (AttributeError, TypeError, ValueError):
        return None


# 出题失败时的兜底模板：宁可给一道朴素但可答的题，也不要当天 0 道题。
# 现场演示时网络一抖 / 模型额度用尽，用户看到「今天没有需要反思的内容」比看到报错更糟。
_TEMPLATE_QUESTIONS = (
    "请用自己的话解释「{name}」，并说明它最容易和哪个概念混淆。",
    "如果要在考试或项目里用上「{name}」，你会怎么向别人讲清楚它？",
    "「{name}」解决的是什么问题？请举一个你自己做过的例子。",
)


def template_question(node_name: str, node_summary: str = "") -> str:
    """按节点名稳定地挑一条模板题：同一节点每次拿到的题一致，便于复现。"""
    name = (node_name or "").strip() or "这个知识点"
    index = sum(ord(ch) for ch in name) % len(_TEMPLATE_QUESTIONS)
    question = _TEMPLATE_QUESTIONS[index].format(name=name)
    summary = (node_summary or "").strip()
    if len(summary) >= 10:
        question += f"（笔记里的说法：{summary[:60]}…）"
    return question


def build_question_reason(node: dict, signals: dict | None) -> str:
    """把「为什么今天问这道题」讲清楚：先讲硬原因（久未复习/掌握度），再补行为信号。"""
    mastery = _to_score(node.get("mastery"), 0.0)
    parts: list[str] = []
    last_reviewed = node.get("last_reviewed")
    days = _days_since(last_reviewed)

    if last_reviewed is None:
        # 0 分的新知识点说「掌握度 0 分」等于什么都没说，讲「还没复习过」才有信息量
        parts.append("还没有复习记录")
    elif mastery < MASTERY_THRESHOLD:
        parts.append(f"掌握度 {mastery:.0f} 分，低于 {MASTERY_THRESHOLD:.0f}")
    elif days is None:
        parts.append("超过 7 天没有复习")
    else:
        parts.append(f"距上次复习 {days:.0f} 天")

    if signals:
        parts.extend(signals.get("reasons") or [])
    return "；".join(parts)


def diversify_by_subject(
    nodes: list[dict], limit: int, per_subject: int = 2
) -> list[dict]:
    """同一天的题尽量分散到不同学科。

    队列按「久未复习」排序时，同一次导入的一章知识点往往挤在一起：
    5 道题全来自材料力学，反思就变成了背同一页书。这里限制单学科最多 2 道，
    不够再按原顺序补齐，保证「有 5 道题」优先于「绝对分散」。
    """
    picked: list[dict] = []
    overflow: list[dict] = []
    used: dict[str, int] = {}
    for node in nodes:
        if len(picked) >= limit:
            break
        subject = str(node.get("subject") or "")
        if used.get(subject, 0) >= per_subject:
            overflow.append(node)
            continue
        used[subject] = used.get(subject, 0) + 1
        picked.append(node)
    if len(picked) < limit:
        picked.extend(overflow[: limit - len(picked)])
    return picked


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
        today_start, tomorrow_start = _local_day_bounds()

        already_today = await self.db.execute(
            select(ReflectionRecord.target_node_id).where(
                ReflectionRecord.user_id == user_id,
                ReflectionRecord.created_at >= today_start,
                ReflectionRecord.created_at < tomorrow_start,
            )
        )
        asked_rows = already_today.all()
        asked_node_ids = {row[0] for row in asked_rows if row[0] is not None}
        if len(asked_rows) >= settings.REFLECTION_DAILY_LIMIT:
            return []

        remaining = settings.REFLECTION_DAILY_LIMIT - len(asked_rows)
        max_questions = min(max_questions, remaining)

        nodes = await self.graph_service.get_nodes_for_review(
            user_id=user_id,
            mastery_threshold=MASTERY_THRESHOLD,
            days_threshold=DAYS_THRESHOLD,
            limit=max_questions * 3,
        )
        nodes = [n for n in nodes if n.get("id") not in asked_node_ids]
        if not nodes:
            return []

        # 弱信号只重排、不改分：先看今天"值得问"的（刚学的、正被讨论的、刚看过的），
        # 同分时再回落到「掌握度低 + 久未复习」。
        signals = await review_signals.collect(self.db, user_id, nodes)
        nodes.sort(
            key=lambda n: (
                -(signals.get(n.get("id"), {}).get("score") or 0.0),
                _to_score(n.get("mastery"), 0.0),
            )
        )
        nodes = diversify_by_subject(nodes, max_questions)

        records = []
        for node in nodes:
            node_id = node.get("id")
            node_name = node.get("name", "未知知识点")
            node_summary = node.get("summary", "")

            question_text, generated_by = await self._make_question(
                node_name, node_summary
            )

            record = ReflectionRecord(
                user_id=user_id,
                question=question_text,
                target_node_id=node_id,
                node_name=node_name,
                reason=build_question_reason(node, signals.get(node_id)),
                generated_by=generated_by,
            )
            self.db.add(record)
            records.append(record)

        await self.db.commit()
        for record in records:
            await self.db.refresh(record)

        return records

    async def _make_question(self, node_name: str, node_summary: str) -> tuple[str, str]:
        """返回 (题干, 生成方式)。模型失败或返回空串时用模板题兜底，绝不让当天空手而归。"""
        try:
            question = await self.ai_service.generate_question(
                node_name=node_name,
                node_summary=node_summary,
            )
            if question and question.strip():
                return question.strip(), "ai"
            logger.warning("模型返回空题目，改用模板题: node=%s", node_name)
        except Exception:  # noqa: BLE001 - 出题失败不应阻断整轮反思
            logger.warning("生成问题失败，改用模板题: node=%s", node_name, exc_info=True)
        return template_question(node_name, node_summary), "template"


    async def get_today_questions(self, user_id: str) -> list[ReflectionRecord]:
        today_start, tomorrow_start = _local_day_bounds()

        result = await self.db.execute(
            select(ReflectionRecord)
            .where(
                ReflectionRecord.user_id == user_id,
                ReflectionRecord.created_at >= today_start,
                ReflectionRecord.created_at < tomorrow_start,
            )
            .order_by(ReflectionRecord.created_at.desc(), ReflectionRecord.id.desc())
        )
        return list(result.scalars().all())

    async def ensure_today_questions(
        self, user_id: str, max_questions: int = MAX_QUESTIONS
    ) -> list[ReflectionRecord]:
        """幂等的「保证今天有题」：已有则原样返回，没有才生成。

        这把锁必须放在服务层：APScheduler 的定时任务直接调服务、不经过路由，
        锁留在路由层时「定时任务」和「用户点开始反思」会并发各生成一套题，
        同一天同一知识点被问两遍。注意 asyncio.Lock 不可重入，调用方不要重复加锁。
        """
        async with _generate_lock(user_id):
            existing = await self.get_today_questions(user_id)
            if existing:
                return existing
            return await self.generate_questions(user_id, max_questions=max_questions)

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
            # 已作答：返回上次的评分明细（含当初的薄弱点与资源），
            # 之前这里恒返回空数组，导致用户重开同一道题只剩一个分数。
            return {
                "mastery_score": record.mastery_score or 0.0,
                "concept_accuracy": record.concept_accuracy or 0.0,
                "logic_completeness": record.logic_completeness or 0.0,
                "example_reasonableness": record.example_reasonableness or 0.0,
                "weak_points": _load_list(record.weak_points),
                "suggestion": record.feedback or "",
                "resources": _load_list(record.resources),
                "already_answered": True,
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

        concept = _to_score(evaluation.get("concept_accuracy", 0.0))
        logic = _to_score(evaluation.get("logic_completeness", 0.0))
        example = _to_score(evaluation.get("example_reasonableness", 0.0))

        weighted_score = (
            concept * WEIGHT_CONCEPT
            + logic * WEIGHT_LOGIC
            + example * WEIGHT_EXAMPLE
        )

        record.answer = answer
        record.is_voice = is_voice
        record.feedback = evaluation.get("suggestion", "")
        record.weak_points = _dump_list(evaluation.get("weak_points"))
        record.resources = _dump_list(evaluation.get("resources"))
        record.mastery_score = weighted_score
        record.concept_accuracy = concept
        record.logic_completeness = logic
        record.example_reasonableness = example
        record.answered_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # 掌握度记账：把「改前 / 改后 / 本次权重」落到这条反思记录上。
        # 复盘时不需要回放公式（图谱初值和历史都在变），直接看当时的账最可信。
        mastery_before: float | None = None
        mastery_after: float | None = None
        mastery_weight: float | None = None
        mastery_synced = True
        if record.target_node_id:
            # 单进程内串行化「读旧值→算新值→写回」，避免同节点并发评分互相覆盖。
            # 多实例部署仍需在 Neo4j 侧做原子写（本项目的部署形态是单容器）。
            async with _mastery_lock(user_id, record.target_node_id):
                try:
                    node = await self.graph_service.get_node_detail(
                        user_id=user_id, node_id=record.target_node_id
                    )
                    old_mastery = float(node.get("mastery") or 0.0) if node else 0.0

                    days_since_review = (
                        _days_since(node.get("last_reviewed")) if node else None
                    )
                    old_weight, new_weight = compute_mastery_weights(
                        old_mastery, days_since_review
                    )
                    new_mastery = (
                        old_mastery * old_weight + weighted_score * new_weight
                    )
                    # 「改前值」和「本次权重」在写回之前就是既定事实，先记账。
                    # 只读图谱写不回去时，用户看到的是「40 → 未写回（本次权重 85%）」，
                    # 而不是含糊的「未留存前后值」——后者会让人以为是老数据的问题。
                    mastery_before = round(old_mastery, 2)
                    mastery_weight = round(new_weight, 4)
                    try:
                        await self.graph_service.update_mastery(
                            user_id=user_id,
                            node_id=record.target_node_id,
                            mastery=new_mastery,
                        )
                        mastery_after = round(new_mastery, 2)
                    except Exception:  # noqa: BLE001
                        # 图谱只读（演示模式）或不可用：评分与「改前值」仍然有效，
                        # 丢掉整次评分比「分数已记录、掌握度未同步」更伤用户。
                        mastery_synced = False
                        logger.warning(
                            "掌握度回写失败，本次评分仍然保留: user=%s node=%s",
                            user_id,
                            record.target_node_id,
                            exc_info=True,
                        )
                except Exception:  # noqa: BLE001
                    mastery_synced = False
                    logger.warning(
                        "读取节点掌握度失败，本次评分仍然保留: user=%s node=%s",
                        user_id,
                        record.target_node_id,
                        exc_info=True,
                    )

        record.mastery_before = mastery_before
        record.mastery_after = mastery_after
        record.mastery_weight = mastery_weight

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
            "mastery_synced": mastery_synced,
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
                "time": _iso_utc(record.answered_at),
                "score": record.mastery_score,
            })
            if record.answered_at is not None:
                entry["_last_time"] = record.answered_at
            timeline.append({
                "time": _iso_utc(record.answered_at),
                "node_id": node_id,
                "node_name": record.node_name or "",
                "score": record.mastery_score,
            })

        for entry in node_map.values():
            entry.pop("_last_time", None)

        return {"nodes": list(node_map.values()), "timeline": timeline}

    async def get_node_mastery_detail(self, user_id: str, node_id: str) -> dict:
        """单个知识点的掌握度溯源：当前值 + 每次反思的账（改前/改后/权重/三维护分）。

        这是回答「这个 62 分是怎么来的」的唯一入口。历史记录里 mastery_before/after
        为空的是记账上线前的数据，如实标为「未记账」，不做回放猜测。
        """
        node = None
        try:
            node = await self.graph_service.get_node_detail(
                user_id=user_id, node_id=node_id
            )
        except Exception:  # noqa: BLE001 - 图谱不可用时仍应能看历史记录
            logger.warning("读取节点详情失败: node=%s", node_id, exc_info=True)

        result = await self.db.execute(
            select(ReflectionRecord)
            .where(
                ReflectionRecord.user_id == user_id,
                ReflectionRecord.target_node_id == node_id,
                ReflectionRecord.answered_at.is_not(None),
            )
            .order_by(ReflectionRecord.answered_at.asc())
        )
        records = list(result.scalars().all())

        timeline = [
            {
                "record_id": r.id,
                "time": _iso_utc(r.answered_at),
                "score": r.mastery_score,
                "concept_accuracy": r.concept_accuracy,
                "logic_completeness": r.logic_completeness,
                "example_reasonableness": r.example_reasonableness,
                "mastery_before": r.mastery_before,
                "mastery_after": r.mastery_after,
                "new_weight": r.mastery_weight,
                "recorded": r.mastery_after is not None,
            }
            for r in records
        ]

        return {
            "node_id": node_id,
            "node_name": (node or {}).get("name") or (records[-1].node_name if records else ""),
            "mastery": _to_score((node or {}).get("mastery"), 0.0),
            "last_reviewed": (node or {}).get("last_reviewed"),
            "review_count": len(records),
            "timeline": timeline,
            "weights": {
                "concept": WEIGHT_CONCEPT,
                "logic": WEIGHT_LOGIC,
                "example": WEIGHT_EXAMPLE,
                "base_new_weight": MASTERY_NEW_WEIGHT,
                "halflife_days": MASTERY_DECAY_HALFLIFE_DAYS,
            },
        }

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
