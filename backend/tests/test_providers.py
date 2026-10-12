import httpx
import pytest

from app.services.providers.base import (
    LLM_ERROR_TYPES,
    close_http_client,
    get_http_client,
)



def test_network_errors_covered_by_degradation():
    assert isinstance(httpx.ConnectError("boom"), LLM_ERROR_TYPES)
    assert isinstance(httpx.ReadTimeout("timeout"), LLM_ERROR_TYPES)
    assert isinstance(httpx.ReadError("reset"), LLM_ERROR_TYPES)


@pytest.mark.asyncio
async def test_shared_http_client_is_reused():
    try:
        first = get_http_client()
        second = get_http_client()
        assert first is second
    finally:
        await close_http_client()