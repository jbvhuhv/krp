"""LLM / Embedding Provider 抽象基类与降级契约。"""

from abc import ABC, abstractmethod

import httpx

from app.core.config import settings

AI_BUSY_MESSAGE = "AI繁忙，请稍后重试"

# 覆盖网络层异常（连接失败 ConnectError、读写中断、超时）与 HTTP 状态异常，
# 使上游模型不可达时统一走降级（status=failed），而不是把 500 抛给用户。
LLM_ERROR_TYPES: tuple[type[Exception], ...] = (
    httpx.TimeoutException,
    httpx.HTTPStatusError,
    httpx.RequestError,
)

DEFAULT_TIMEOUT = 60.0
# 建连单独设短超时：上游不可达时快速失败，避免占满连接池并拖垮请求处理
CONNECT_TIMEOUT = 10.0

_shared_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """进程内共享的 httpx 客户端，复用连接池，避免每次调用新建 client。

    仅在应用运行时（单事件循环）使用；被关闭后自动重建。
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=CONNECT_TIMEOUT),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=60.0,
            ),
        )
    return _shared_client


async def close_http_client() -> None:
    """关闭共享客户端（应用关停时调用）。"""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None


def degraded_result(message: str = AI_BUSY_MESSAGE, **extra) -> dict:
    """构造统一的降级返回对象，供非流式调用方判断 status=failed。"""
    result: dict = {"status": "failed", "message": message}
    result.update(extra)
    return result


def json_call_kwargs(temperature: float | None = 0) -> dict:
    """构造「要求模型返回 JSON」的调用参数。

    temperature 默认 0：评分与抽取必须可复现——同一份答案提交两次不该得到两个分数。
    上游若不支持 response_format，MaasProvider 会自动去掉该参数重试一次。
    """
    kwargs: dict = {}
    if settings.LLM_JSON_MODE:
        kwargs["response_format"] = {"type": "json_object"}
    if temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, prompt: str, **kwargs) -> str:
        ...

    @abstractmethod
    async def stream_chat(self, prompt: str, **kwargs):
        ...


class VisionProvider(ABC):
    """多模态（视觉）Provider：输入图片 base64 与文本指令，返回模型输出文本。"""

    @abstractmethod
    async def describe_image(self, image_b64: str, mime: str, prompt: str) -> str:
        ...


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        ...
