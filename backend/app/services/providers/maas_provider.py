import httpx

from app.core.logger import get_logger
from app.services.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    get_http_client,
)

logger = get_logger(__name__)


class MaasProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _ensure_configured(self) -> None:
        if not self.base_url or not self.api_key:
            raise RuntimeError(
                "AI 服务未配置：请在 backend/.env 设置 LLM_BASE_URL/LLM_API_KEY"
                "（或 MAAS_BASE_URL/MAAS_API_KEY 及 LLM_MODEL）"
            )

    async def _chat_once(self, prompt: str, kwargs: dict) -> str:
        client = get_http_client()
        resp = await client.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                **kwargs,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def chat(self, prompt: str, **kwargs) -> str:
        self._ensure_configured()
        try:
            return await self._chat_once(prompt, kwargs)
        except httpx.HTTPStatusError as exc:
            # 部分 OpenAI 兼容端点不认 response_format，会直接 400/422。
            # 此时退化成纯文本调用再试一次，避免把一次「格式参数不兼容」升级成抽取失败。
            if "response_format" in kwargs and exc.response.status_code in (400, 422):
                logger.warning(
                    "上游不支持 response_format，降级为纯文本调用：%s",
                    exc.response.status_code,
                )
                fallback = {k: v for k, v in kwargs.items() if k != "response_format"}
                return await self._chat_once(prompt, fallback)
            raise

    async def stream_chat(self, prompt: str, **kwargs):
        self._ensure_configured()
        client = get_http_client()
        async with client.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                **kwargs,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]


class MaasEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def embed(self, text: str) -> list[float]:
        client = get_http_client()
        resp = await client.post(
            f"{self.base_url}/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": text},
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload["data"][0]["embedding"]
