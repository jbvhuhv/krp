from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


class _FakeSessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class _FakeAvatarService:
    def __init__(self, avatar, events):
        self._avatar = avatar
        self._events = events

    async def get_by_avatar_id(self, avatar_id):
        return self._avatar

    async def stream_answer(self, avatar, query, history=None, visitor_id=None):
        for event in self._events:
            yield event


def _patch(monkeypatch, avatar, events):
    import app.api.v1.endpoints.avatar as avatar_mod

    monkeypatch.setattr(avatar_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(
        avatar_mod, "build_avatar_service", lambda db: _FakeAvatarService(avatar, events)
    )


def test_websocket_rejects_missing_avatar(monkeypatch):
    _patch(monkeypatch, None, [])

    client = TestClient(app)
    with client.websocket_connect("/api/v1/avatar/chat/missing") as ws:
        msg = ws.receive_json()
        assert msg == {"type": "error", "message": "分身不存在或已下线"}


def test_websocket_online_welcome_and_stream(monkeypatch):
    avatar = SimpleNamespace(status="online", welcome_message="你好呀")
    events = [
        {"type": "chunk", "content": "你好"},
        {"type": "done", "answer": "你好"},
    ]
    _patch(monkeypatch, avatar, events)

    client = TestClient(app)
    with client.websocket_connect("/api/v1/avatar/chat/av1") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["message"] == "你好呀"

        ws.send_text("你的知识库有啥")
        assert ws.receive_json()["type"] == "chunk"
        done = ws.receive_json()
        assert done["type"] == "done"
        assert done["answer"] == "你好"
