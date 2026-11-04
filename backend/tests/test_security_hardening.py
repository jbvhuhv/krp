"""安全响应头 / 接口文档开关 / 限流降级 的回归用例。

这三项都是「线上才生效、本地不容易察觉」的加固，必须用测试钉住，
否则下次重构很容易被无声回退。
"""

import pytest

from app.core import rate_limit
from app.core.config import settings


async def test_security_headers_present(client):
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    # 明文 HTTP 下绝不能下发 HSTS，否则浏览器会把 http 也强制升级、本地直接打不开
    assert "strict-transport-security" not in resp.headers


async def test_hsts_only_behind_https_proxy(client):
    """生产是 Caddy 终止 TLS 后反代，应用侧只能靠 X-Forwarded-Proto 判断。"""
    resp = await client.get("/health", headers={"x-forwarded-proto": "https"})

    assert resp.headers["strict-transport-security"].startswith("max-age=")


async def test_api_docs_hidden_by_default(client):
    """演示环境常常 DEBUG=true，文档开关必须独立于 DEBUG。"""
    if settings.ENABLE_API_DOCS:  # 本地 .env 显式打开时跳过，避免误报
        pytest.skip("当前环境显式启用了 API 文档")

    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/openapi.json")).status_code == 404


class TestRateLimitFallback:
    """Redis 不可用时必须降级为进程内计数，而不是静默放行。"""

    async def test_counts_in_memory_when_redis_down(self, monkeypatch):
        rate_limit.reset_all_in_memory()

        async def _boom(*_args, **_kwargs):
            raise ConnectionError("redis down")

        monkeypatch.setattr(rate_limit.redis_client, "incr", _boom)
        monkeypatch.setattr(rate_limit.redis_client, "get", _boom)

        key = "test:fallback:counter"
        assert await rate_limit.incr(key, 60) == 1
        assert await rate_limit.incr(key, 60) == 2
        assert await rate_limit.get(key) == 2

        await rate_limit.reset(key)
        assert await rate_limit.get(key) == 0

    async def test_expired_key_resets_to_zero(self, monkeypatch):
        rate_limit.reset_all_in_memory()

        async def _boom(*_args, **_kwargs):
            raise ConnectionError("redis down")

        monkeypatch.setattr(rate_limit.redis_client, "incr", _boom)
        monkeypatch.setattr(rate_limit.redis_client, "get", _boom)

        key = "test:fallback:expire"
        await rate_limit.incr(key, 1)
        # ttl=1 秒；这里不 sleep，直接把过期时间改成过去，验证清理逻辑
        count, _ = rate_limit._MEMORY[key]
        rate_limit._MEMORY[key] = (count, 0.0)
        assert await rate_limit.get(key) == 0


async def test_malformed_stream_is_not_500(client):
    """流式接口收到坏请求体时应返回 4xx，而不是 500（避免把校验失败当成服务故障）。"""
    resp = await client.post("/api/v1/brainstorm/suggest/stream", json={})
    assert resp.status_code in (401, 422)


class _FakeWS:
    """够 _client_ip 用的最小 WebSocket 替身。"""

    def __init__(self, headers=None, host="127.0.0.1"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})()


def test_client_ip_prefers_last_forwarded_hop():
    """反代场景下要取 X-Forwarded-For 的最后一跳。

    浏览器 → Caddy → 容器，`websocket.client.host` 恒为反代地址；若按它计数，
    「每人每分钟 20 条」会退化成「全站每分钟 20 条」，两个访客互相锁死。
    取最后一跳而不是第一跳，是因为客户端可以自己塞伪造前缀，只有反代追加的那段可信。
    """
    from app.api.v1.endpoints.avatar import _client_ip

    ws = _FakeWS({"x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert _client_ip(ws) == "203.0.113.9"

    ws_real_ip = _FakeWS({"x-real-ip": "198.51.100.7"})
    assert _client_ip(ws_real_ip) == "198.51.100.7"

    # 无反代头时退回连接地址
    assert _client_ip(_FakeWS()) == "127.0.0.1"
