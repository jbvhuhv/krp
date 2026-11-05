"""只读演示环境的读接口、出题幂等、时间序列化、短信配额回滚。

这些问题的共同点是「单测都能过，但换个环境/换个入口就露馅」：
只读图谱的读接口被写保护拦截、定时任务绕过路由层的锁、
naive 时间被浏览器当成本地时间、网关失败烧掉当日短信额度。
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.reflection import ReflectionRecord
from app.services.reflection_service import ReflectionService


def _reflection_service(db, graph, ai):
    return ReflectionService(db=db, ai_service=ai, graph_service=graph)


def _ai_stub(question="解释一下这个概念"):
    class _AI:
        async def generate_question(self, node_name, node_summary=""):
            return question

        async def evaluate_answer(self, **kwargs):
            return {
                "concept_accuracy": 80,
                "logic_completeness": 60,
                "example_reasonableness": 40,
                "suggestion": "补充例子",
                "weak_points": ["缺少反例"],
                "resources": ["教材第 3 章"],
            }

    return _AI()


# --------------------------------------------------------------- 演示模式只读读接口


async def test_local_graph_supports_study_profile():
    """六维画像不能在演示模式 403：只读图谱写不了，但不是「不能读」。"""
    from app.services.graph.local_service import LocalGraphService

    service = LocalGraphService()
    profile = await service.get_study_profile(service._data.demo_user_id)

    assert profile["total"] > 0
    names = [d["name"] for d in profile["dimensions"]]
    assert names == ["掌握度", "熟练度", "巩固度", "复习覆盖", "知识广度", "知识体量"]
    assert all(0 <= d["value"] <= 100 for d in profile["dimensions"])


async def test_study_profile_unknown_user_is_empty():
    from app.services.graph.local_service import LocalGraphService

    service = LocalGraphService()
    profile = await service.get_study_profile("not-the-demo-user")

    assert profile == {"total": 0, "dimensions": []}


# ------------------------------------------------------------------- 出题幂等


async def test_ensure_today_questions_is_idempotent(test_db, mock_graph_service):
    mock_graph_service.get_nodes_for_review = AsyncMock(
        return_value=[
            {"id": "ens-1", "name": "知识点一", "mastery": 10},
            {"id": "ens-2", "name": "知识点二", "mastery": 20},
        ]
    )
    service = _reflection_service(test_db, mock_graph_service, _ai_stub())

    first = await service.ensure_today_questions("ensure-user")
    second = await service.ensure_today_questions("ensure-user")

    assert [r.id for r in first] == [r.id for r in second]
    rows = (
        await test_db.execute(
            select(ReflectionRecord).where(ReflectionRecord.user_id == "ensure-user")
        )
    ).scalars().all()
    assert len(rows) == len(first)


async def test_ensure_today_questions_serializes_concurrent_calls(
    test_db, mock_graph_service
):
    """定时任务与用户手动刷新同时触发时，只能有一套题。"""
    mock_graph_service.get_nodes_for_review = AsyncMock(
        return_value=[{"id": "race-1", "name": "并发知识点", "mastery": 5}]
    )

    class _SlowAI:
        async def generate_question(self, node_name, node_summary=""):
            await asyncio.sleep(0.01)
            return f"{node_name} 是什么？"

    service = _reflection_service(test_db, mock_graph_service, _SlowAI())

    results = await asyncio.gather(
        service.ensure_today_questions("race-user"),
        service.ensure_today_questions("race-user"),
    )

    assert results[0][0].id == results[1][0].id
    rows = (
        await test_db.execute(
            select(ReflectionRecord).where(ReflectionRecord.user_id == "race-user")
        )
    ).scalars().all()
    assert len(rows) == 1


# ----------------------------------------------------------------- 记账与时间


async def test_mastery_ledger_keeps_before_value_when_graph_readonly(
    test_db, mock_graph_service
):
    """只读图谱：改前值仍要记账，不能和「记账上线前的旧数据」混为一谈。"""
    from app.core.exceptions import ForbiddenException

    test_db.add(
        ReflectionRecord(
            id="ro-q2",
            user_id="ro-user",
            question="解释概念",
            node_name="概念",
            target_node_id="node-ro2",
        )
    )
    await test_db.commit()

    mock_graph_service.get_node_detail = AsyncMock(
        return_value={"id": "node-ro2", "mastery": 40.0, "last_reviewed": None}
    )
    mock_graph_service.update_mastery = AsyncMock(
        side_effect=ForbiddenException("只读图谱")
    )

    service = _reflection_service(test_db, mock_graph_service, _ai_stub())
    result = await service.evaluate_answer("ro-user", "ro-q2", "答案")

    record = await test_db.get(ReflectionRecord, "ro-q2")
    assert result["mastery_synced"] is False
    assert record.mastery_before == 40.0
    assert record.mastery_after is None
    assert record.mastery_weight is not None


async def test_mastery_detail_time_is_utc_iso(test_db, mock_graph_service):
    """时间必须带 Z，否则浏览器把它当本地时间，时间线整体偏 8 小时。"""
    test_db.add(
        ReflectionRecord(
            id="iso-q1",
            user_id="iso-user",
            question="问",
            answer="答",
            node_name="牛顿第二定律",
            target_node_id="node-iso",
            mastery_score=50.0,
            mastery_before=40.0,
            mastery_after=46.0,
            mastery_weight=0.6,
            answered_at=datetime(2026, 11, 5, 3, 56, 31,
                                 tzinfo=timezone.utc).replace(tzinfo=None),
        )
    )
    await test_db.commit()
    mock_graph_service.get_node_detail = AsyncMock(return_value=None)

    service = _reflection_service(test_db, mock_graph_service, _ai_stub())
    data = await service.get_node_mastery_detail("iso-user", "node-iso")

    assert data["timeline"][0]["time"].endswith("Z")


# ------------------------------------------------------------------ 短信配额


async def test_sms_gateway_failure_refunds_daily_quota(client, monkeypatch):
    """网关失败要连带退回「今日已发送次数」，否则连续失败会烧完当天额度。"""
    from app.api.v1.endpoints import auth as auth_mod
    from app.core.config import settings
    from app.services import sms_service

    store: dict[str, str] = {}

    class _Redis:
        async def get(self, key):
            return store.get(key)

        async def setex(self, key, ttl, value):
            store[key] = value

        async def incr(self, key):
            store[key] = str(int(store.get(key, "0")) + 1)
            return int(store[key])

        async def decr(self, key):
            store[key] = str(int(store.get(key, "0")) - 1)
            return int(store[key])

        async def expire(self, key, ttl):
            return True

        async def delete(self, key):
            store.pop(key, None)

    monkeypatch.setattr(auth_mod, "redis_client", _Redis())
    monkeypatch.setattr(settings, "SMS_WEBHOOK_URL", "https://sms.example.com/send")
    monkeypatch.setattr(
        sms_service,
        "deliver_code",
        AsyncMock(side_effect=sms_service.SmsSendFailed("down")),
    )

    resp = await client.post("/api/v1/auth/send-code", json={"phone": "13900006666"})

    assert resp.status_code == 502
    # 计数被退回（decr 到 0 时键会被清掉，所以「不存在」也算退干净）
    daily = [v for k, v in store.items() if k.startswith("sms:daily:")]
    assert all(int(v) <= 0 for v in daily)
    assert not [k for k in store if k.startswith("sms:rate:")]
    assert not [k for k in store if k.startswith("sms:code:")]
