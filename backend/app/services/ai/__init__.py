from app.prompts.avatar import (
    AVATAR_CHAT_PROMPT,
    AVATAR_SMALLTALK_PROMPT,
    TONE_DESCRIPTIONS,
)
from app.prompts.brainstorm import (
    BRAINSTORM_GENERATE_PROMPT,
    BRAINSTORM_GUIDE_PROMPT,
    BRAINSTORM_HINT_PROMPT,
    BRAINSTORM_VERIFY_PROMPT,
)
from app.prompts.extraction import EXTRACTION_PROMPT
from app.prompts.pet import PET_CHAT_PROMPT, PET_SYSTEM_PROMPTS
from app.prompts.reflection import EVALUATION_PROMPT, QUESTION_GENERATION_PROMPT
from app.services.ai.avatar_ai import AvatarMixin
from app.services.ai.base import (
    AIServiceBase,
    create_embedding_provider,
    create_llm_provider,
    create_vision_provider,
)
from app.services.ai.brainstorm_ai import BrainstormMixin
from app.services.ai.extraction_ai import ExtractionMixin
from app.services.ai.pet_ai import PetMixin
from app.services.ai.quiz_ai import QuizMixin
from app.services.ai.scoring_ai import ScoringMixin
from app.services.providers.base import EmbeddingProvider, LLMProvider

__all__ = [
    "AIService",
    "LLMClient",
    "EmbeddingClient",
    "LLMProvider",
    "EmbeddingProvider",
    "create_ai_service",
    "create_llm_provider",
    "create_embedding_provider",
    "create_vision_provider",
    "EXTRACTION_PROMPT",
    "QUESTION_GENERATION_PROMPT",
    "EVALUATION_PROMPT",
    "AVATAR_CHAT_PROMPT",
    "AVATAR_SMALLTALK_PROMPT",
    "TONE_DESCRIPTIONS",
    "PET_SYSTEM_PROMPTS",
    "PET_CHAT_PROMPT",
    "BRAINSTORM_VERIFY_PROMPT",
    "BRAINSTORM_HINT_PROMPT",
    "BRAINSTORM_GUIDE_PROMPT",
    "BRAINSTORM_GENERATE_PROMPT",
]

# 兼容旧引用：Provider 抽象基类此前以别名形式导出。
LLMClient = LLMProvider
EmbeddingClient = EmbeddingProvider


class AIService(
    AIServiceBase,
    ExtractionMixin,
    QuizMixin,
    ScoringMixin,
    AvatarMixin,
    PetMixin,
    BrainstormMixin,
):
    pass


def create_ai_service() -> AIService:
    return AIService(llm=create_llm_provider(), embedding=create_embedding_provider())
