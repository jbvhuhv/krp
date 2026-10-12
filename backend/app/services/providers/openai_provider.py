"""OpenAI Provider 预留空壳。

后续接入 OpenAI（或其它 OpenAI 兼容端点）时在此实现；当前仅占位，
调用即抛出 NotImplementedError，明确表示尚未支持。
"""

from app.services.providers.base import EmbeddingProvider, LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def chat(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError("OpenAIProvider.chat 尚未实现")

    async def stream_chat(self, prompt: str, **kwargs):
        raise NotImplementedError("OpenAIProvider.stream_chat 尚未实现")


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("OpenAIEmbeddingProvider.embed 尚未实现")
