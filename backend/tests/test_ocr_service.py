import httpx
import pytest

from app.services.ocr_service import OcrError, OcrNotConfiguredError, OcrService
from app.services.providers.base import VisionProvider

pytestmark = pytest.mark.asyncio


class _FakeVisionProvider(VisionProvider):
    def __init__(self, result: str = "文字", error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    async def describe_image(self, image_b64: str, mime: str, prompt: str) -> str:
        self.calls.append((image_b64, mime, prompt))
        if self.error:
            raise self.error
        return self.result


async def test_recognize_bytes_not_configured():
    service = OcrService(provider=None)
    with pytest.raises(OcrNotConfiguredError):
        await service.recognize_bytes(b"bytes", ".png")


async def test_recognize_bytes_success_strips_and_maps_mime():
    provider = _FakeVisionProvider(result="  识别文字  ")
    service = OcrService(provider=provider)

    text = await service.recognize_bytes(b"abc", ".jpg")

    assert text == "识别文字"
    _, mime, prompt = provider.calls[0]
    assert mime == "image/jpeg"
    assert prompt


async def test_recognize_bytes_wraps_http_error():
    error = httpx.HTTPStatusError(
        "boom",
        request=httpx.Request("POST", "http://example.com"),
        response=httpx.Response(500),
    )
    service = OcrService(provider=_FakeVisionProvider(error=error))

    with pytest.raises(OcrError):
        await service.recognize_bytes(b"abc", ".png")