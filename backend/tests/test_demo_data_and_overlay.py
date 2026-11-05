"""演示数据的量纲、分布与掌握度回写。

这类问题的共同点：**代码是对的，数据是错的**，普通单测永远覆盖不到。
要么在评审现场才发现「555 个知识点掌握度全是 0%」「每天的题一模一样」，
要么改一次演示数据就悄悄退回原样。所以直接对随仓库分发的演示数据本身做断言。
"""

import json
import os
import sqlite3

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.graph.local_service import LocalGraphService, review_sort_key

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEMO_GRAPH = os.path.join(BACKEND_DIR, "demo", "neo4j-demo.jsonl")
DEMO_DB = os.path.join(BACKEND_DIR, "demo", "krp-demo.db")


def _knowledge_nodes() -> list[dict]:
    nodes: list[dict] = []
    with open(DEMO_GRAPH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") != "node":
                continue
            props = rec.get("props") or {}
            if props.get("node_type") == "knowledge":
                nodes.append(props)
    return nodes


def test_demo_graph_mastery_uses_percent_scale():
    """量纲必须是 0–100：0.8 分和 80 分是两个世界，混用会让画像整体塌成 0。"""
    values = [float(n.get("mastery") or 0.0) for n in _knowledge_nodes()]

    assert values, "演示图谱不应为空"
    assert max(values) <= 100.0
    # 除了「从未复习」的 0 分，不允许再出现 0–1 的比例值
    assert not [v for v in values if 0 < v <= 1.0]


def test_demo_graph_mastery_is_not_flat():
    """不能整份都是 0 分：否则每日反思的理由清一色「还没有复习记录」。"""
    nodes = _knowledge_nodes()
    values = [float(n.get("mastery") or 0.0) for n in nodes]
    reviewed = [n for n in nodes if n.get("last_reviewed")]

    avg = sum(values) / len(values)
    assert 20.0 <= avg <= 70.0
    assert len([v for v in values if v == 0.0]) < len(values) * 0.5
    assert len(reviewed) > len(nodes) * 0.5


def test_review_queue_prefers_overdue_over_never_reviewed():
    """排序先看「多久没复习」，再看掌握度，否则新知识点会长期霸占队列。"""
    overdue_solid = review_sort_key(mastery=80.0, days=30.0)
    brand_new = review_sort_key(mastery=0.0, days=None)
    slightly_stale = review_sort_key(mastery=30.0, days=10.0)
    fresh_weak = review_sort_key(mastery=10.0, days=1.0)

    assert overdue_solid < brand_new
    assert slightly_stale < fresh_weak


async def test_local_graph_mastery_writeback_survives_restart(test_engine):
    """演示模式下答题要能改变掌握度，并且重启进程后仍然有效。"""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    service = LocalGraphService(session_factory=session_factory)
    user_id = service._data.demo_user_id

    first = (await service.get_nodes_for_review(user_id, limit=1))[0]
    updated = await service.update_mastery(user_id, first["id"], 92.5)

    assert updated["mastery"] == 92.5
    # 新实例 = 进程重启：覆盖层要能从库里读回来
    restarted = LocalGraphService(session_factory=session_factory)
    detail = await restarted.get_node_detail(user_id, first["id"])
    assert detail["mastery"] == 92.5
    assert detail["last_reviewed"]

    # 刚复习过的节点不该立刻又排在队首
    queue = await restarted.get_nodes_for_review(user_id, limit=5)
    assert first["id"] not in [n["id"] for n in queue]


async def test_answer_updates_mastery_in_demo_mode(tmp_path):
    """答题 → 掌握度写回 → 账本对得上：演示环境的整条闭环。"""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.reflection import ReflectionRecord
    from app.models.user import Base, User
    from app.services.reflection_service import ReflectionService

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'demo.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    graph = LocalGraphService(session_factory=session_factory)
    user_id = graph._data.demo_user_id
    node = (await graph.get_nodes_for_review(user_id, limit=1))[0]

    class _AI:
        async def evaluate_answer(self, **_kwargs):
            return {
                "concept_accuracy": 90,
                "logic_completeness": 80,
                "example_reasonableness": 70,
                "suggestion": "ok",
                "weak_points": [],
                "resources": [],
            }

    try:
        async with session_factory() as db:
            db.add(User(id=user_id, phone="13900000001"))
            db.add(
                ReflectionRecord(
                    id="ans-q1",
                    user_id=user_id,
                    question="解释一下",
                    node_name=node["name"],
                    target_node_id=node["id"],
                )
            )
            await db.commit()

            service = ReflectionService(db=db, ai_service=_AI(), graph_service=graph)
            result = await service.evaluate_answer(user_id, "ans-q1", "我的回答")

            assert result["mastery_synced"] is True
            record = await db.get(ReflectionRecord, "ans-q1")
            # 账本：改前值 = 图谱原值；本次得分高于原值，改后值必须上升
            assert record.mastery_before == round(float(node["mastery"]), 2)
            assert record.mastery_after > record.mastery_before
            assert 0.6 <= record.mastery_weight <= 0.85

            detail = await graph.get_node_detail(user_id, node["id"])
            # 图谱存原值、账本存两位小数，允许 0.01 的记账舍入差
            assert detail["mastery"] == pytest.approx(record.mastery_after, abs=0.01)
    finally:
        await engine.dispose()


def test_demo_db_has_mastery_ledger():
    """演示库的已答记录要带账本，否则「掌握度溯源」抽屉打开是空的。"""
    con = sqlite3.connect(f"file:{DEMO_DB.replace(os.sep, '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT node_name, mastery_score, mastery_before, mastery_after, target_node_id
            FROM reflection_records
            WHERE answer IS NOT NULL AND mastery_score IS NOT NULL
            """
        ).fetchall()
    finally:
        con.close()

    assert rows, "演示库应当有已答的反思记录"
    for row in rows:
        # 0–1 比例的量纲已被换算过：0.85 这种值不该再出现
        assert float(row["mastery_score"]) > 1.0 or float(row["mastery_score"]) == 0.0
        assert row["target_node_id"], f"{row['node_name']} 的答题记录要能对上知识点"
        assert row["mastery_before"] is not None
        assert row["mastery_after"] is not None


def test_daily_questions_spread_across_subjects():
    """同日 5 道题不该全来自同一章，否则反思变成背同一页书。"""
    from app.services.reflection_service import diversify_by_subject

    nodes = [
        {"id": "1", "subject": "材料力学"},
        {"id": "2", "subject": "材料力学"},
        {"id": "3", "subject": "材料力学"},
        {"id": "4", "subject": "操作系统"},
        {"id": "5", "subject": "Python编程"},
    ]

    picked = diversify_by_subject(nodes, 5)

    assert [n["id"] for n in picked[:4]] == ["1", "2", "4", "5"]
    assert len(picked) == 5  # 不够分散时按原顺序补齐
