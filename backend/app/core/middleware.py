"""请求级中间件：为每次请求生成并透传 trace_id。"""

import uuid

from app.core.logger import reset_trace_id, set_trace_id

TRACE_ID_HEADER = "x-trace-id"


class TraceIdMiddleware:
    """纯 ASGI 中间件，保证 trace_id 在同一上下文中对下游生效。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = None
        for key, value in scope.get("headers") or []:
            if key == b"x-trace-id":
                trace_id = value.decode("latin-1")
                break
        trace_id = trace_id or uuid.uuid4().hex

        scope.setdefault("state", {})["trace_id"] = trace_id
        token = set_trace_id(trace_id)

        async def send_with_trace(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append(
                    (TRACE_ID_HEADER.encode("latin-1"), trace_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            reset_trace_id(token)
