"""OpenAI 兼容的视觉 Provider 实现。

适配任意遵循 OpenAI Chat Completions 协议、支持图片输入的多模态模型
（如 GLM-4V、Qwen-VL、GPT-4o 等）：将图片以 base64 data URL 形式随文本
指令一起发送，取回模型输出的文字。
"""


from app.services.providers.base import VisionProvider, get_http_client


class OpenAICompatibleVisionProvider(VisionProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _ensure_configured(self) -> None:
        if not self.base_url or not self.api_key or not self.model:
            raise RuntimeError(
                "OCR 服务未配置：请在 backend/.env 设置 "
                "OCR_BASE_URL/OCR_API_KEY/OCR_MODEL"
            )

    async def describe_image(self, image_b64: str, mime: str, prompt: str) -> str:
        self._ensure_configured()
        client = get_http_client()
        resp = await client.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime};base64,{image_b64}"
                                },
                            },
                        ],
                    }
                ],
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
