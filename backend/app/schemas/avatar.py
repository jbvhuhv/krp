from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import DEFAULT_WELCOME_MESSAGE
from app.schemas.common import UtcDateTime


class AvatarConfig(BaseModel):
    tone: Literal["rigorous", "lively", "concise"] = "rigorous"
    welcome_message: str = Field(DEFAULT_WELCOME_MESSAGE, max_length=500)
    knowledge_scope: list[str] = Field(default=[], max_length=50)
    avatar_url: str | None = Field(default=None, max_length=512)


class KnowledgeProfile(BaseModel):
    domain_distribution: dict[str, int] = {}
    mastery_overview: dict = {}
    reflection_style: dict = {}
    summary: str = ""
    generated_at: UtcDateTime | None = None


class AvatarPublishOut(BaseModel):
    avatar_id: str
    share_token: str
    share_url: str
    status: str = "online"


class AvatarOut(BaseModel):
    avatar_id: str
    status: str
    tone: str
    welcome_message: str
    knowledge_scope: list[str] = []
    avatar_url: str | None = None
    profile: KnowledgeProfile | None = None


class SourceRef(BaseModel):
    node_id: str
    name: str
    summary: str = ""
    subject: str | None = None
    mastery: float = 0.0
    score: float = 0.0
    source_note_id: str | None = None
    note_title: str | None = None


class AvatarStats(BaseModel):
    total_conversations: int
    today_conversations: int = 0
    total_messages: int
    top_questions: list[dict] = []


class ConversationSummary(BaseModel):
    visitor_id: str
    display_name: str
    message_count: int = 0
    question_count: int = 0
    last_message_at: UtcDateTime | None = None
    last_question: str | None = None


class ConversationList(BaseModel):
    conversations: list[ConversationSummary] = []


class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: UtcDateTime | None = None
    sources: list = []


class ConversationDetail(BaseModel):
    visitor_id: str
    display_name: str
    messages: list[ChatMessageOut] = []


class ChatEvent(BaseModel):
    type: str
    message: str | None = None
    content: str | None = None
    answer: str | None = None
    sources: list[SourceRef] = []
