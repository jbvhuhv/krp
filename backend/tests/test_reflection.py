from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.reflection import ReflectionRecord, ReflectionSchedule
from app.services.reflection_service import (
    ReflectionService,
    compute_mastery_weights,
)


@pytest.fixture
def mock_ai_service():
    service = AsyncMock()
    service.generate_question = AsyncMock(return_value="请解释牛顿第二定律的本质含义。")
    service.evaluate_answer = AsyncMock(return_value={
        "concept_accuracy": 85.0,
        "logic_completeness": 70.0,
        "example_reasonableness": 60.0,
        "weak_points": ["对加速度概念理解不够深入"],
        "suggestion": "建议复习加速度与力的关系",
        "resources": ["《大学物理》第三章"],
    })
    return service


@pytest.fixture
async def reflection_service(test_db, mock_ai_service, mock_graph_service):
    return ReflectionService(
        db=test_db,
        ai_service=mock_ai_service,
        graph_service=mock_graph_service,
    )


class TestReflectionServiceGenerateQuestions:
    async def test_generate_questions_from_review_nodes(
        self, reflection_service, mock_graph_service, mock_ai_service, test_db
    ):
        mock_graph_service.get_nodes_for_review = AsyncMock(return_value=[
            {"id": "node-1", "name": "牛顿第二定律", "summary": "F=ma"},
            {"id": "node-2", "name": "动量守恒", "summary": "系统总动量不变"},
        ])

        records = await reflection_service.generate_questions("user-1")

        assert len(records) == 2
        assert records[0].question == "请解释牛顿第二定律的本质含义。"
        assert records[0].target_node_id == "node-1"
        assert records[0].node_name == "牛顿第二定律"
        mock_graph_service.get_nodes_for_review.assert_called_once()
        assert mock_ai_service.generate_question.call_count == 2

    async def test_generate_questions_no_nodes(
        self, reflection_service, mock_graph_service
    ):
        mock_graph_service.get_nodes_for_review = AsyncMock(return_value=[])

        records = await reflection_service.generate_questions("user-1")

        assert len(records) == 0

    async def test_generate_questions_ai_failure_uses_template(
        self, reflection_service, mock_graph_service, mock_ai_service
    ):
        """模型不可用时不能让当天 0 道题：改用模板题，并如实标注 generated_by。"""
        mock_graph_service.get_nodes_for_review = AsyncMock(return_value=[
            {"id": "node-1", "name": "知识点A", "summary": ""},
        ])
        mock_ai_service.generate_question = AsyncMock(side_effect=Exception("AI error"))

        records = await reflection_service.generate_questions("user-1")

        assert len(records) == 1
        assert "知识点A" in records[0].question
        assert records[0].generated_by == "template"
        # 出题理由要能说清「为什么是它」
        assert records[0].reason


class TestReflectionServiceGetTodayQuestions:
    async def test_get_today_questions_empty(self, reflection_service):
        questions = await reflection_service.get_today_questions("user-1")
        assert len(questions) == 0

    async def test_get_today_questions_returns_unanswered(
        self, reflection_service, test_db
    ):
        record = ReflectionRecord(
            user_id="user-1",
            question="什么是牛顿第二定律？",
            target_node_id="node-1",
            node_name="牛顿第二定律",
        )
        test_db.add(record)
        await test_db.commit()

        questions = await reflection_service.get_today_questions("user-1")

        assert len(questions) == 1
        assert questions[0].question == "什么是牛顿第二定律？"

    async def test_get_today_questions_includes_answered(
        self, reflection_service, test_db
    ):
        record = ReflectionRecord(
            user_id="user-1",
            question="已回答的问题",
            answer="这是回答",
            mastery_score=80.0,
        )
        test_db.add(record)
        await test_db.commit()

        questions = await reflection_service.get_today_questions("user-1")

        assert len(questions) == 1
        assert questions[0].answer is not None


def test_compute_mastery_weights_time_and_difficulty():
    # 刚复习 + 高掌握度（简单）：新权重取基准值
    base_old, base_new = compute_mastery_weights(100.0, None)
    assert base_new == pytest.approx(0.6)
    assert base_old == pytest.approx(0.4)

    # 权重之和恒为 1，且落在 [基准, 上限] 区间
    for mastery, days in ((0.0, 0.0), (30.0, 3.0), (70.0, 30.0), (90.0, 365.0)):
        old_w, new_w = compute_mastery_weights(mastery, days)
        assert old_w + new_w == pytest.approx(1.0)
        assert 0.6 <= new_w <= 0.85

    # 时间越久，新观测权重越大
    _, fresh = compute_mastery_weights(60.0, 0.0)
    _, stale = compute_mastery_weights(60.0, 30.0)
    assert stale > fresh

    # 越难（掌握度越低），新观测权重越大
    _, easy = compute_mastery_weights(95.0, None)
    _, hard = compute_mastery_weights(5.0, None)
    assert hard > easy


class TestReflectionServiceEvaluateAnswer:

    async def test_evaluate_answer_success(
        self, reflection_service, mock_graph_service, mock_ai_service, test_db
    ):
        record = ReflectionRecord(
            user_id="user-1",
            question="解释牛顿第二定律",
            target_node_id="node-1",
            node_name="牛顿第二定律",
        )
        test_db.add(record)
        await test_db.commit()
        await test_db.refresh(record)

        mock_graph_service.get_node_detail = AsyncMock(return_value={
            "id": "node-1", "mastery": 50.0,
        })
        mock_graph_service.update_mastery = AsyncMock(return_value={"mastery": 76.0})

        result = await reflection_service.evaluate_answer(
            user_id="user-1",
            question_id=record.id,
            answer="F=ma，力等于质量乘以加速度",
        )

        assert result is not None
        assert result["mastery_score"] == pytest.approx(85 * 0.4 + 70 * 0.35 + 60 * 0.25)
        assert result["concept_accuracy"] == 85.0
        assert result["logic_completeness"] == 70.0
        assert result["example_reasonableness"] == 60.0
        mock_graph_service.update_mastery.assert_called_once()
        update_kwargs = mock_graph_service.update_mastery.call_args.kwargs
        expected_score = 85 * 0.4 + 70 * 0.35 + 60 * 0.25
        # 无 last_reviewed（视为刚复习）时时间因子为 0，权重仅由难度（掌握度 50）决定
        old_weight, new_weight = compute_mastery_weights(50.0, None)
        expected_mastery = 50.0 * old_weight + expected_score * new_weight
        assert update_kwargs["mastery"] == pytest.approx(expected_mastery)

    async def test_evaluate_answer_question_not_found(self, reflection_service):
        result = await reflection_service.evaluate_answer(
            user_id="user-1",
            question_id="nonexistent",
            answer="回答",
        )
        assert result is None

    async def test_evaluate_answer_no_target_node(
        self, reflection_service, mock_graph_service, test_db
    ):
        record = ReflectionRecord(
            user_id="user-1",
            question="通用问题",
            target_node_id=None,
            node_name=None,
        )
        test_db.add(record)
        await test_db.commit()
        await test_db.refresh(record)

        result = await reflection_service.evaluate_answer(
            user_id="user-1",
            question_id=record.id,
            answer="回答内容",
        )

        assert result is not None
        mock_graph_service.update_mastery.assert_not_called()


class TestReflectionServiceGetHistory:
    async def test_get_history_empty(self, reflection_service):
        result = await reflection_service.get_history("user-1")
        assert result["total"] == 0
        assert len(result["items"]) == 0

    async def test_get_history_with_records(
        self, reflection_service, test_db
    ):
        for i in range(3):
            record = ReflectionRecord(
                user_id="user-1",
                question=f"问题{i}",
                answer=f"回答{i}",
                mastery_score=70.0 + i,
            )
            test_db.add(record)
        await test_db.commit()

        result = await reflection_service.get_history("user-1")

        assert result["total"] == 3
        assert len(result["items"]) == 3

    async def test_get_history_pagination(
        self, reflection_service, test_db
    ):
        for i in range(5):
            record = ReflectionRecord(
                user_id="user-1",
                question=f"问题{i}",
            )
            test_db.add(record)
        await test_db.commit()

        result = await reflection_service.get_history("user-1", limit=2, offset=0)

        assert result["total"] == 5
        assert len(result["items"]) == 2


class TestReflectionServiceSchedule:
    async def test_get_schedule_creates_default(self, reflection_service):
        schedule = await reflection_service.get_schedule("user-1")

        assert schedule.frequency == "daily"
        assert schedule.time_window == "20:00-21:00"

    async def test_update_schedule_creates_new(self, reflection_service):
        schedule = await reflection_service.update_schedule(
            user_id="user-1",
            frequency="weekly",
            time_window="09:00-10:00",
        )

        assert schedule.frequency == "weekly"
        assert schedule.time_window == "09:00-10:00"

    async def test_update_schedule_modifies_existing(
        self, reflection_service, test_db
    ):
        existing = ReflectionSchedule(
            user_id="user-1",
            frequency="daily",
            time_window="20:00-21:00",
        )
        test_db.add(existing)
        await test_db.commit()

        schedule = await reflection_service.update_schedule(
            user_id="user-1",
            frequency="custom",
            time_window="08:00-09:00",
        )

        assert schedule.frequency == "custom"
        assert schedule.time_window == "08:00-09:00"


class TestReflectionAPIGetToday:
    async def test_get_today_returns_existing_questions(
        self, client, mock_reflection_service
    ):
        mock_reflection_service.get_today_questions = AsyncMock(return_value=[
            ReflectionRecord(
                id="q-1",
                user_id="test-user-0001",
                question="什么是牛顿第二定律？",
                target_node_id="node-1",
                node_name="牛顿第二定律",
            ),
        ])

        response = await client.get("/api/v1/reflection/today")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["question"] == "什么是牛顿第二定律？"

    async def test_get_today_does_not_generate_when_empty(
        self, client, mock_reflection_service
    ):
        mock_reflection_service.get_today_questions = AsyncMock(return_value=[])

        response = await client.get("/api/v1/reflection/today")

        assert response.status_code == 200
        mock_reflection_service.generate_questions.assert_not_called()

    async def test_generate_today_generates_when_empty(
        self, client, mock_reflection_service
    ):
        mock_reflection_service.get_today_questions = AsyncMock(return_value=[])
        mock_reflection_service.generate_questions = AsyncMock(return_value=[])

        response = await client.post("/api/v1/reflection/today/generate")

        assert response.status_code == 200
        mock_reflection_service.generate_questions.assert_called_once()

    async def test_generate_today_skips_when_existing(
        self, client, mock_reflection_service
    ):
        mock_reflection_service.get_today_questions = AsyncMock(return_value=[
            ReflectionRecord(
                id="q-1",
                user_id="test-user-0001",
                question="已有题",
                target_node_id="node-1",
                node_name="牛顿第二定律",
            ),
        ])
        mock_reflection_service.generate_questions = AsyncMock(return_value=[])

        response = await client.post("/api/v1/reflection/today/generate")

        assert response.status_code == 200
        mock_reflection_service.generate_questions.assert_not_called()


class TestReflectionAPISubmitAnswer:
    async def test_submit_answer_success(self, client, mock_reflection_service):
        mock_reflection_service.evaluate_answer = AsyncMock(return_value={
            "mastery_score": 76.0,
            "concept_accuracy": 85.0,
            "logic_completeness": 70.0,
            "example_reasonableness": 60.0,
            "weak_points": ["概念理解不足"],
            "suggestion": "建议复习",
            "resources": ["资料1"],
        })

        response = await client.post("/api/v1/reflection/answer", json={
            "question_id": "q-1",
            "answer": "F=ma",
        })

        assert response.status_code == 200
        body = response.json()
        assert body["mastery_score"] == 76.0
        assert body["concept_accuracy"] == 85.0

    async def test_submit_answer_not_found(self, client, mock_reflection_service):
        mock_reflection_service.evaluate_answer = AsyncMock(return_value=None)

        response = await client.post("/api/v1/reflection/answer", json={
            "question_id": "nonexistent",
            "answer": "回答",
        })

        assert response.status_code == 404

    async def test_submit_answer_with_voice(self, client, mock_reflection_service):
        mock_reflection_service.evaluate_answer = AsyncMock(return_value={
            "mastery_score": 80.0,
            "concept_accuracy": 80.0,
            "logic_completeness": 80.0,
            "example_reasonableness": 80.0,
            "weak_points": [],
            "suggestion": "",
            "resources": [],
        })

        response = await client.post("/api/v1/reflection/answer", json={
            "question_id": "q-1",
            "answer": "语音转文字内容",
            "is_voice": True,
        })

        assert response.status_code == 200
        call_kwargs = mock_reflection_service.evaluate_answer.call_args.kwargs
        assert call_kwargs["is_voice"] is True


class TestReflectionAPIHistory:
    async def test_get_history_default(self, client, mock_reflection_service):
        mock_reflection_service.get_history = AsyncMock(return_value={
            "items": [],
            "total": 0,
        })

        response = await client.get("/api/v1/reflection/history")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0

    async def test_get_history_with_pagination(self, client, mock_reflection_service):
        mock_reflection_service.get_history = AsyncMock(return_value={
            "items": [],
            "total": 10,
        })

        response = await client.get("/api/v1/reflection/history?limit=5&offset=5")

        assert response.status_code == 200
        call_kwargs = mock_reflection_service.get_history.call_args.kwargs
        assert call_kwargs["limit"] == 5
        assert call_kwargs["offset"] == 5


class TestReflectionAPIMastery:
    async def test_get_mastery(self, client, mock_reflection_service):
        mock_reflection_service.get_mastery_trend = AsyncMock(return_value={
            "nodes": [
                {"node_id": "n1", "node_name": "牛顿第二定律", "mastery": 80.0, "history": []},
            ],
            "timeline": [],
        })

        response = await client.get("/api/v1/reflection/mastery")

        assert response.status_code == 200
        body = response.json()
        assert len(body["nodes"]) == 1
        assert body["nodes"][0]["node_name"] == "牛顿第二定律"


class TestReflectionAPISchedule:
    async def test_get_schedule(self, client, mock_reflection_service):
        from datetime import datetime, timezone
        schedule = ReflectionSchedule(
            id="sched-1",
            user_id="test-user-0001",
            frequency="daily",
            time_window="20:00-21:00",
        )
        schedule.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        mock_reflection_service.get_schedule = AsyncMock(return_value=schedule)

        response = await client.get("/api/v1/reflection/schedule")

        assert response.status_code == 200
        body = response.json()
        assert body["frequency"] == "daily"

    async def test_update_schedule(self, client, mock_reflection_service):
        from datetime import datetime, timezone
        schedule = ReflectionSchedule(
            id="sched-1",
            user_id="test-user-0001",
            frequency="weekly",
            time_window="09:00-10:00",
        )
        schedule.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        mock_reflection_service.update_schedule = AsyncMock(return_value=schedule)

        response = await client.put("/api/v1/reflection/schedule", json={
            "frequency": "weekly",
            "time_window": "09:00-10:00",
        })

        assert response.status_code == 200
        body = response.json()
        assert body["frequency"] == "weekly"
        assert body["time_window"] == "09:00-10:00"

@pytest.mark.asyncio
async def test_get_mastery_trend_unifies_ema_with_graph(reflection_service, test_db):
    base = datetime(2026, 1, 1, 12, 0, 0)
    test_db.add_all([
        ReflectionRecord(
            user_id="trend-user", question="q1", answer="a",
            target_node_id="n1", node_name="牛顿第二定律",
            mastery_score=40.0, answered_at=base, created_at=base,
        ),
        ReflectionRecord(
            user_id="trend-user", question="q2", answer="a",
            target_node_id="n1", node_name="牛顿第二定律",
            mastery_score=80.0,
            answered_at=base + timedelta(days=30),
            created_at=base + timedelta(days=30),
        ),
    ])
    await test_db.commit()

    trend = await reflection_service.get_mastery_trend("trend-user")
    assert len(trend["nodes"]) == 1
    node = trend["nodes"][0]

    # 与图谱侧同一 EMA：首次 old=0 无时间因子；第二次间隔 30 天触发时间衰减加权
    _, w1 = compute_mastery_weights(0.0, None)
    m1 = 40.0 * w1
    _, w2 = compute_mastery_weights(m1, 30.0)
    m2 = m1 * (1 - w2) + 80.0 * w2
    assert node["mastery"] == pytest.approx(m2)
    # 不再是「最近一次会话分」的口径
    assert node["mastery"] != pytest.approx(80.0)
    # 时间线仍保留原始会话分
    assert trend["timeline"][-1]["score"] == 80.0
    assert "_last_time" not in node
