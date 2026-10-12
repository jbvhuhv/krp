from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class ReflectionQuestion(BaseModel):
    id: str
    question: str
    target_node_id: str | None = None
    node_name: str | None = None


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
