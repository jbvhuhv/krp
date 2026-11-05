"""反思出题的弱信号。

设计边界（很重要，别越界）：
- 弱信号**只决定今天先问哪几个知识点**，不参与掌握度数值的计算。
- 掌握度的强信号仍然只有一个：反思答题得分。行为信号如果也能改分数，
  「掌握度」就变成不可解释的混合指标，答辩时说不清。
- 所有信号都取自已有数据（笔记上传时间、分身回答的引用、节点查看埋点），
  没有信号时返回空字典，出题顺序回落到「掌握度低 + 久未复习」。

存在的理由：过去出题只看掌握度，而掌握度只由答题更新——不答题的图谱永远不动，
反思每天重复问同一批节点。加入弱信号后，用户在其它地方的行为也能让出题"呼吸"。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.avatar import Avatar, ChatMessage
from app.models.note import Note
from app.models.reflection import NodeView

# 笔记上传后多久内算「刚学」
FRESH_NOTE_DAYS = 3
# 分身引用、节点查看的回看窗口
ACTIVITY_DAYS = 7

FRESH_NOTE_BOOST = 2.0
AVATAR_HIT_BOOST = 1.5
AVATAR_HIT_BOOST_CAP = 3.0
VIEW_BOOST = 0.5
VIEW_BOOST_CAP = 1.5


def _since(days: int) -> datetime:
    """库里存的是 naive UTC（server_default=func.now()），比较时统一去掉时区。"""
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


async def _fresh_note_ids(db: AsyncSession, user_id: str) -> set[str]:
    rows = await db.execute(
        select(Note.id).where(
            Note.user_id == user_id,
            Note.upload_time >= _since(FRESH_NOTE_DAYS),
        )
    )
    return set(rows.scalars().all())


async def _avatar_hit_counts(
    db: AsyncSession, user_id: str, wanted: set[str]
) -> dict[str, int]:
    """数一数分身最近回答里引用了哪些知识点。

    sources 是 JSON 列，SQLite/PG 的跨方言 JSON 查询写法差异较大，这里直接取最近
    500 条到内存里统计——单用户量级下代价可忽略，换来的是一份不挑方言的实现。
    """
    rows = await db.execute(
        select(ChatMessage.sources)
        .join(Avatar, ChatMessage.avatar_id == Avatar.id)
        .where(
            Avatar.user_id == user_id,
            ChatMessage.role == "assistant",
            ChatMessage.created_at >= _since(ACTIVITY_DAYS),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(500)
    )
    counts: dict[str, int] = {}
    for (sources,) in rows.all():
        if not isinstance(sources, list):
            continue
        seen: set[str] = set()
        for item in sources:
            if not isinstance(item, dict):
                continue
            node_id = item.get("node_id")
            # 同一条回答引用同一节点多次只算一次，避免长回答把权重刷满
            if node_id in wanted and node_id not in seen:
                counts[node_id] = counts.get(node_id, 0) + 1
                seen.add(node_id)
    return counts


async def _view_counts(
    db: AsyncSession, user_id: str, wanted: set[str]
) -> dict[str, int]:
    rows = await db.execute(
        select(NodeView.node_id, sql_func.count(NodeView.id))
        .where(
            NodeView.user_id == user_id,
            NodeView.viewed_at >= _since(ACTIVITY_DAYS),
            NodeView.node_id.in_(wanted),
        )
        .group_by(NodeView.node_id)
    )
    return {node_id: count for node_id, count in rows.all()}


async def collect(
    db: AsyncSession, user_id: str, nodes: list[dict]
) -> dict[str, dict]:
    """返回 {node_id: {"score": float, "reasons": [str]}}，无信号时不返回该键。"""
    wanted = {n["id"] for n in nodes if n.get("id")}
    if not wanted:
        return {}

    note_of = {n["id"]: n.get("source_note_id") for n in nodes if n.get("id")}
    fresh_notes = await _fresh_note_ids(db, user_id)
    avatar_hits = await _avatar_hit_counts(db, user_id, wanted)
    view_counts = await _view_counts(db, user_id, wanted)

    result: dict[str, dict] = {}
    for node_id in wanted:
        score = 0.0
        reasons: list[str] = []

        note_id = note_of.get(node_id)
        if note_id and note_id in fresh_notes:
            score += FRESH_NOTE_BOOST
            reasons.append(f"来自最近 {FRESH_NOTE_DAYS} 天上传的笔记，趁热复习")

        hits = avatar_hits.get(node_id, 0)
        if hits:
            score += min(hits * AVATAR_HIT_BOOST, AVATAR_HIT_BOOST_CAP)
            reasons.append(f"分身最近 {ACTIVITY_DAYS} 天引用过 {hits} 次")

        views = view_counts.get(node_id, 0)
        if views:
            score += min(views * VIEW_BOOST, VIEW_BOOST_CAP)
            reasons.append(f"最近 {ACTIVITY_DAYS} 天查看过 {views} 次")

        if reasons:
            result[node_id] = {"score": round(score, 2), "reasons": reasons}

    return result
