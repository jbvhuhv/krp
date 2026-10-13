"""OpenAI 兼容的视觉 Provider 实现。

适配任意遵循 OpenAI Chat Completions 协议、支持图片输入的多模态模型
（如 GLM-4V、Qwen-VL、Qwen-Omni、GPT-4o 等）：将图片以 base64 data URL 形式
随文本指令一起发送，取回模型输出的文字。

``OCR_MODEL`` 支持逗号分隔的候选链，例如：

    OCR_MODEL=qwen3.5-omni-flash-2026-03-15,qwen3.5-omni-plus,qwen3.8-omni-flash

按顺序尝试，遇到「免费额度用尽 / 限流 / 模型不可用」等可切换错误时自动换下一个，
这样单个模型的免费额度耗尽不会导致图片笔记整体不可用。
"""

import httpx

from app.core.logger import get_logger
from app.services.providers.base import VisionProvider, get_http_client

logger = get_logger(__name__)


class OpenAICompatibleVisionProvider(VisionProvider):
    # 这些状态码代表"换一个模型可能就好了"（额度用尽、限流、模型下线、服务端异常）
    FALLBACK_STATUS = {402, 403, 404, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        # 候选链：OCR_MODEL 允许写多个模型，用逗号分隔
        self.models = [m.strip() for m in (model or "").split(",") if m.strip()]
        self.model = self.models[0] if self.models else ""
        self.timeout = timeout

    def _ensure_configured(self) -> None:
        if not self.base_url or not self.api_key or not self.models:
            raise RuntimeError(
                "OCR 服务未配置：请在 backend/.env 设置 "
                "OCR_BASE_URL/OCR_API_KEY/OCR_MODEL"
            )

    def _payload(self, model: str, image_b64: str, mime: str, prompt: str) -> dict:
        return {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                        },
                    ],
                }
            ],
        }

    async def describe_image(self, image_b64: str, mime: str, prompt: str) -> str:
        self._ensure_configured()
        client = get_http_client()
        last_exc: Exception | None = None
        for index, model in enumerate(self.models):
            try:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=self._payload(model, image_b64, mime, prompt),
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                if index > 0:
                    logger.info(
                        "OCR 已切换到候选模型 %s（第 %d 个）", model, index + 1
                    )
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                is_last = index == len(self.models) - 1
                if status in self.FALLBACK_STATUS and not is_last:
                    logger.warning(
                        "OCR 模型 %s 不可用（HTTP %s），切换下一个候选", model, status
                    )
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("OCR 模型候选链为空")
