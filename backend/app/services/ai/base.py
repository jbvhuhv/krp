import json

from app.core.config import settings
from app.services.providers.base import EmbeddingProvider, LLMProvider, VisionProvider
from app.services.providers.maas_provider import MaasEmbeddingProvider, MaasProvider
from app.services.providers.openai_provider import (
    OpenAIEmbeddingProvider,
    OpenAIProvider,
)
from app.services.providers.vision_provider import OpenAICompatibleVisionProvider


class AIServiceBase:
    def __init__(self, llm: LLMProvider, embedding: EmbeddingProvider | None = None):
        self.llm = llm
        self.embedding = embedding

    async def embed(self, text: str) -> list[float]:
        if self.embedding is None:
            raise RuntimeError("Embedding client 未配置")
        return await self.embedding.embed(text)

    @staticmethod
    def _parse_stream_token(raw: str) -> str:
        text = raw.strip()
        if not text:
            return ""
        if text == "[DONE]":
            return ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        choices = payload.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if content:
            return content
        message = choices[0].get("message") or {}
        return message.get("content", "") or ""


def create_llm_provider() -> LLMProvider:
    provider = (settings.LLM_PROVIDER or "maas").strip().lower()
    if provider == "maas":
        return MaasProvider(
            api_key=settings.LLM_API_KEY or settings.MAAS_API_KEY,
            base_url=settings.LLM_BASE_URL or settings.MAAS_BASE_URL,
            model=settings.LLM_MODEL or settings.MAAS_MODEL,
        )
    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
        )
    raise ValueError(f"不支持的 LLM_PROVIDER：{settings.LLM_PROVIDER!r}")


def create_vision_provider() -> VisionProvider | None:
    if not settings.OCR_BASE_URL or not settings.OCR_API_KEY or not settings.OCR_MODEL:
        return None
    return OpenAICompatibleVisionProvider(
        api_key=settings.OCR_API_KEY,
        base_url=settings.OCR_BASE_URL,
        model=settings.OCR_MODEL,
    )


def create_embedding_provider() -> EmbeddingProvider | None:
    provider = (settings.LLM_PROVIDER or "maas").strip().lower()
    if provider == "openai":
        if not settings.LLM_BASE_URL:
            return None
        return OpenAIEmbeddingProvider(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
        )
    if not settings.MAAS_BASE_URL:
        return None
    return MaasEmbeddingProvider(
        api_key=settings.MAAS_API_KEY,
        base_url=settings.MAAS_BASE_URL,
        model=settings.MAAS_EMBEDDING_MODEL,
    )
