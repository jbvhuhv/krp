from app.services.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    get_http_client,
)


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

    async def chat(self, prompt: str, **kwargs) -> str:
        self._ensure_configured()
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
