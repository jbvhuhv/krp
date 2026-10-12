"""图片笔记 OCR 服务：将图片交由多模态模型识别为纯文本。

复用 LLM Provider 抽象层中新增的 ``VisionProvider``，具体端点由
``OCR_BASE_URL/OCR_API_KEY/OCR_MODEL`` 配置，模型可替换为任意支持
视觉的 OpenAI 兼容多模态模型。
"""

import base64
import os

from app.core.logger import get_logger
from app.core.prompt_manager import prompt_manager
from app.services.providers.base import LLM_ERROR_TYPES, VisionProvider

logger = get_logger(__name__)

MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class OcrError(RuntimeError):
    """OCR 调用失败（服务异常、超时等）。"""


class OcrNotConfiguredError(OcrError):
    """未配置 OCR 服务，无法识别图片。"""


class OcrService:
    def __init__(self, provider: VisionProvider | None):
        self.provider = provider

    async def recognize_bytes(self, data: bytes, ext: str) -> str:
        """识别图片字节流的文字；未配置或调用失败时抛 OcrError。"""
        if self.provider is None:
            raise OcrNotConfiguredError(
                "图片识别服务未配置，请联系管理员配置 OCR 模型"
                "（OCR_BASE_URL/OCR_API_KEY/OCR_MODEL）"
            )
        mime = MIME_BY_EXT.get(ext.lower(), "image/png")
        image_b64 = base64.b64encode(data).decode("ascii")
        prompt = prompt_manager.get_ocr_prompt()
        try:
            text = await self.provider.describe_image(image_b64, mime, prompt)
        except LLM_ERROR_TYPES as exc:
            logger.warning("OCR 服务调用失败：%s", exc)
            raise OcrError("图片识别服务暂时不可用，请稍后重试") from exc
        return (text or "").strip()

    async def recognize(self, file_path: str) -> str:
        """识别本地图片文件的文字。"""
        ext = os.path.splitext(file_path)[1].lower()
        with open(file_path, "rb") as f:
            data = f.read()
        return await self.recognize_bytes(data, ext)
