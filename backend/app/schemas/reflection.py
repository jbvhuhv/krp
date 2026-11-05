from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class ReflectionQuestion(BaseModel):
    id: str
    question: str
    target_node_id: str | None = None
    node_name: str | None = None
    answered: bool = False
    # 为什么今天问这道题（掌握度 / 久未复习 / 弱信号），前端展示成一行说明
    reason: str | None = None
    # ai：模型生成；template：模型不可用时用模板题兜底
    generated_by: str | None = None


class AnswerSubmit(BaseModel):
    question_id: str
    answer: str = Field(..., min_length=1, max_length=5000)
    is_voice: bool = False


class FeedbackOut(BaseModel):
    mastery_score: float
    concept_accuracy: float = 0.0
    logic_completeness: float = 0.0
    example_reasonableness: float = 0.0
    weak_points: list[str] = []
    suggestion: str = ""
    resources: list[str] = []
    # true 表示这道题此前已作答，本次返回的是缓存的评分（不会二次调用模型）
    already_answered: bool = False
    # false 表示评分已记录，但图谱里的掌握度没能同步（演示只读图谱 / 图库不可用）
    mastery_synced: bool = True


class ReflectionHistoryItem(BaseModel):
    id: str
    question: str
    answer: str | None = None
    feedback: str | None = None
    mastery_score: float | None = None
    target_node_id: str | None = None
    node_name: str | None = None
    is_voice: bool = False
    created_at: UtcDateTime
    answered_at: UtcDateTime | None = None


class ReflectionHistory(BaseModel):
    items: list[ReflectionHistoryItem]
    total: int


class MasteryTrendItem(BaseModel):
    node_id: str
    node_name: str
    mastery: float
    history: list[dict]


class MasteryTrend(BaseModel):
    nodes: list[MasteryTrendItem]
    timeline: list[dict]


class ScheduleUpdate(BaseModel):
    frequency: str = Field("daily", max_length=20)
    time_window: str = Field("20:00-21:00", max_length=20)


class ScheduleOut(BaseModel):
    id: str
    user_id: str
    frequency: str
    time_window: str
    updated_at: UtcDateTime


class NodeMasteryEntry(BaseModel):
    """一次反思对某个知识点掌握度的影响（评分当场记账，不做事后回放）。"""

    record_id: str
    time: str | None = None
    score: float | None = None
    concept_accuracy: float | None = None
    logic_completeness: float | None = None
    example_reasonableness: float | None = None
    mastery_before: float | None = None
    mastery_after: float | None = None
    new_weight: float | None = None
    # false = 记账字段上线前的历史记录，只有分数、没有前后值
    recorded: bool = False


class NodeMasteryWeights(BaseModel):
    concept: float
    logic: float
    example: float
    base_new_weight: float
    halflife_days: float


class NodeMasteryDetail(BaseModel):
    node_id: str
    node_name: str = ""
    mastery: float = 0.0
    last_reviewed: Any = None
    review_count: int = 0
    timeline: list[NodeMasteryEntry] = []
    weights: NodeMasteryWeights
