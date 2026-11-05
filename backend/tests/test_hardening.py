"""针对本轮加固新增的回归测试。

覆盖：
1. 抽取/评分走结构化输出（response_format）与 temperature=0；
2. 评分结果里模型把数组写成字符串时能收敛；
3. 已作答的题返回当初的薄弱点/资源，且不重复调用模型；
4. 上传配额；
5. 调度器解析用户时段与频率。
"""

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.models.reflection import ReflectionRecord
from app.services.ai.extraction_ai import ExtractionMixin
from app.services.ai.scoring_ai import ScoringMixin
from app.services.providers.base import json_call_kwargs
from app.services.reflection_service import ReflectionService


class _FakeLLM:
    """记录 kwargs 的假 Provider，用来断言结构化输出参数确实传下去了。"""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[dict] = []

    async def chat(self, prompt: str, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.reply


class _Extractor(ExtractionMixin):
    def __init__(self, llm):
        self.llm = llm


class _Scorer(ScoringMixin):
    def __init__(self, llm):
        self.llm = llm


def test_json_call_kwargs_enables_json_mode():
    kwargs = json_call_kwargs()
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["temperature"] == 0


def test_json_call_kwargs_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_JSON_MODE", False)
    kwargs = json_call_kwargs()
    assert "response_format" not in kwargs
    # 温度仍然要固定：评分必须可复现
    assert kwargs["temperature"] == 0


async def test_extraction_requests_json_mode():
    llm = _FakeLLM('{"nodes": [], "categories": [], "edges": []}')
    await _Extractor(llm).extract_knowledge("随便一段笔记")

    assert llm.calls, "未调用模型"
    assert llm.calls[0]["response_format"] == {"type": "json_object"}
    assert llm.calls[0]["temperature"] == 0


async def test_scoring_requests_json_mode_and_coerces_string_lists():
    llm = _FakeLLM(
        '{"concept_accuracy": "85分", "logic_completeness": 70, '
        '"example_reasonableness": "优", '
        '"weak_points": "1. 加速度理解不到位\\n2. 没有举例", '
        '"suggestion": "复习第三章", "resources": "《大学物理》"}'
    )
    result = await _Scorer(llm).evaluate_answer("牛顿第二定律", "解释一下", "F=ma")

    assert llm.calls[0]["response_format"] == {"type": "json_object"}
    # 字符串形式的数组必须收敛成 list[str]，否则前端 v-for 会逐字渲染
    assert result["weak_points"] == ["1. 加速度理解不到位", "2. 没有举例"]
    assert result["resources"] == ["《大学物理》"]
    assert result["concept_accuracy"] == "85分"  # 由 service 层的 _to_score 兜底


@pytest.fixture
def _service(test_db, mock_graph_service):
    ai_service = AsyncMock()
    return ReflectionService(
        db=test_db, ai_service=ai_service, graph_service=mock_graph_service
    ), ai_service


async def test_answered_question_returns_saved_details_without_calling_llm(_service):
    service, ai_service = _service
    record = ReflectionRecord(
        user_id="user-1",
        question="解释动量守恒",
        answer="系统不受外力时总动量不变",
        mastery_score=72.0,
        concept_accuracy=80.0,
        weak_points='["没有提到适用条件"]',
        resources='["《大学物理》第四章"]',
        feedback="补充适用条件",
    )
    service.db.add(record)
    await service.db.commit()
    await service.db.refresh(record)

    result = await service.evaluate_answer("user-1", record.id, "再答一次")

    assert result["already_answered"] is True
    assert result["weak_points"] == ["没有提到适用条件"]
    assert result["resources"] == ["《大学物理》第四章"]
    # 已作答不再重复调用模型，避免同一道题拿到第二个分数
    ai_service.evaluate_answer.assert_not_awaited()


async def test_weak_points_are_persisted_after_evaluation(_service):
    service, ai_service = _service
    ai_service.evaluate_answer = AsyncMock(
        return_value={
            "concept_accuracy": 80.0,
            "logic_completeness": 70.0,
            "example_reasonableness": 60.0,
            "weak_points": ["漏掉了边界条件"],
            "suggestion": "再看一遍定义",
            "resources": ["教材 P32"],
        }
    )
    record = ReflectionRecord(user_id="user-2", question="解释极限", node_name="极限")
    service.db.add(record)
    await service.db.commit()
    await service.db.refresh(record)

    await service.evaluate_answer("user-2", record.id, "当 x 趋近某值时函数值趋近某值")

    await service.db.refresh(record)
    assert record.weak_points == '["漏掉了边界条件"]'
    assert record.resources == '["教材 P32"]'


async def test_upload_quota_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DAILY_LIMIT", 0)
    response = await client.post(
        "/api/v1/notes/upload",
        files={"file": ("note.md", b"# hello", "text/markdown")},
    )
    assert response.status_code == 429
    assert "最多上传" in response.json()["detail"]


def test_scheduler_parses_user_window_and_frequency():
    from app.scheduler import _frequency_to_day_of_week, _parse_time_window

    assert _parse_time_window("19:30-21:00") == (19, 30)
    assert _parse_time_window("") == (
        settings.REFLECTION_CRON_HOUR,
        settings.REFLECTION_CRON_MINUTE,
    )
    assert _parse_time_window("bad") == (
        settings.REFLECTION_CRON_HOUR,
        settings.REFLECTION_CRON_MINUTE,
    )
    assert _frequency_to_day_of_week("daily") is None
    assert _frequency_to_day_of_week("weekdays") == "mon-fri"
    assert _frequency_to_day_of_week("weekly") == "sun"
