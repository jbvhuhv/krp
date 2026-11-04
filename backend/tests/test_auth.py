from unittest.mock import patch

import pytest

from app.core.config import settings

pytestmark = pytest.mark.asyncio


class MockRedis:
    def __init__(self):
        self.store = {}
        self.ttl = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttl[key] = ttl

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        self.ttl[key] = ttl

    async def delete(self, key):
        self.store.pop(key, None)

    def reset(self):
        self.store.clear()
        self.ttl.clear()


@pytest.fixture
def mock_redis():
    r = MockRedis()
    # 登录失败计数已收敛到 app.core.rate_limit（Redis 不可用时进程内兜底），两个模块都要替换
    with patch("app.api.v1.endpoints.auth.redis_client", r), patch(
        "app.core.rate_limit.redis_client", r
    ):
        yield r


async def test_send_code_success(client, mock_redis):
    resp = await client.post("/api/v1/auth/send-code", json={"phone": "13800138000"})
    assert resp.status_code == 200
    assert "已发送" in resp.json()["message"]
    code_key = "sms:code:13800138000"
    assert mock_redis.store.get(code_key) is not None
    assert len(mock_redis.store[code_key]) == 6


async def test_send_code_rate_limit(client, mock_redis):
    await client.post("/api/v1/auth/send-code", json={"phone": "13900139000"})
    resp = await client.post("/api/v1/auth/send-code", json={"phone": "13900139000"})
    assert resp.status_code == 429
    assert "频繁" in resp.json()["detail"]


async def test_send_code_daily_limit(client, mock_redis):
    phone = "13700137000"
    for _ in range(5):
        mock_redis.store.pop(f"sms:rate:{phone}", None)
        await client.post("/api/v1/auth/send-code", json={"phone": phone})
    mock_redis.store.pop(f"sms:rate:{phone}", None)
    resp = await client.post("/api/v1/auth/send-code", json={"phone": phone})
    assert resp.status_code == 429
    assert "上限" in resp.json()["detail"]


async def test_send_code_invalid_phone(client, mock_redis):
    resp = await client.post("/api/v1/auth/send-code", json={"phone": "12345"})
    assert resp.status_code == 422


async def test_login_new_user_auto_register(client, mock_redis):
    phone = "13800138001"
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    code = mock_redis.store[f"sms:code:{phone}"]
    resp = await client.post("/api/v1/auth/login", json={"phone": phone, "code": code})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"

    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["phone"] == phone


async def test_login_existing_user(client, mock_redis):
    phone = "13800138002"
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    code1 = mock_redis.store[f"sms:code:{phone}"]
    resp1 = await client.post("/api/v1/auth/login", json={"phone": phone, "code": code1})
    assert resp1.status_code == 200

    mock_redis.store.pop(f"sms:rate:{phone}", None)
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    code2 = mock_redis.store[f"sms:code:{phone}"]
    resp2 = await client.post("/api/v1/auth/login", json={"phone": phone, "code": code2})
    assert resp2.status_code == 200


async def test_login_wrong_code(client, mock_redis):
    phone = "13800138003"
    await client.post("/api/v1/auth/send-code", json={"phone": phone})
    resp = await client.post("/api/v1/auth/login", json={"phone": phone, "code": "000000"})
    assert resp.status_code == 401
    assert "验证码错误" in resp.json()["detail"]


async def test_login_master_code(client, mock_redis):
    phone = "13800138004"
    resp = await client.post("/api/v1/auth/login", json={"phone": phone, "code": "123456"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_master_code_phone_not_allowlisted(client, mock_redis):
    """万能码只认白名单手机号：名单外的号码即使验证码正确也必须 401。

    回归用例：修复前只比对 code 不比对 phone，任何人拿公开万能码 + 对方手机号即可登录对方账号。
    """
    resp = await client.post(
        "/api/v1/auth/login", json={"phone": "13700000000", "code": "123456"}
    )
    assert resp.status_code == 401
    assert "验证码错误" in resp.json()["detail"]


async def test_login_fail_count_limits_when_redis_down(client, monkeypatch):
    """Redis 不可用时仍必须限流：缓存故障不能变成「可以无限枚举验证码」。"""

    class BrokenRedis:
        async def get(self, *args, **kwargs):
            raise TimeoutError("redis down")

        async def setex(self, *args, **kwargs):
            raise TimeoutError("redis down")

        async def incr(self, *args, **kwargs):
            raise TimeoutError("redis down")

        async def expire(self, *args, **kwargs):
            raise TimeoutError("redis down")

        async def delete(self, *args, **kwargs):
            raise TimeoutError("redis down")

    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 2)
    with patch("app.api.v1.endpoints.auth.redis_client", BrokenRedis()), patch(
        "app.core.rate_limit.redis_client", BrokenRedis()
    ):
        for _ in range(2):
            resp = await client.post(
                "/api/v1/auth/login", json={"phone": "13700000001", "code": "000000"}
            )
            assert resp.status_code == 401
        resp = await client.post(
            "/api/v1/auth/login", json={"phone": "13700000001", "code": "000000"}
        )
        assert resp.status_code == 429


async def test_login_invalid_phone(client, mock_redis):
    resp = await client.post("/api/v1/auth/login", json={"phone": "123", "code": "123456"})
    assert resp.status_code == 400


async def test_get_me_without_token(client, mock_redis):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
