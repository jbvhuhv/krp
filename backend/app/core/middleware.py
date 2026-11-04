"""请求级中间件：为每次请求生成并透传 trace_id，并补齐安全响应头。"""

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


class SecurityHeadersMiddleware:
    """补齐基础安全响应头（纯 ASGI 实现）。

    为什么不用 `@app.middleware("http")`（BaseHTTPMiddleware）：它会给每个响应再套一层
    任务组与队列，StreamingResponse（本项目的 SSE 构思接口）容易出现「攒够一批才下发」，
    流式效果退化。这里直接在 send 上改写 http.response.start，零缓冲、零额外协程。
    """

    _STATIC_HEADERS = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        # 麦克风放开给自身（宠物语音输入用 Web Speech API），其余一律关闭
        (b"permissions-policy", b"geolocation=(), camera=(), microphone=(self)"),
        (b"cross-origin-opener-policy", b"same-origin"),
    )
    _HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_https = scope.get("scheme") == "https"
        if not is_https:
            # 生产是 Caddy 终止 TLS 后反代到 127.0.0.1，应用侧看到的 scheme 是 http，
            # 只能靠反代透传的 X-Forwarded-Proto 判断，否则 HSTS 永远不会下发。
            for key, value in scope.get("headers") or []:
                if key == b"x-forwarded-proto":
                    is_https = value.split(b",")[0].strip() == b"https"
                    break

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {key.lower() for key, _ in headers}
                for key, value in self._STATIC_HEADERS:
                    if key not in existing:
                        headers.append((key, value))
                if is_https and self._HSTS[0] not in existing:
                    headers.append(self._HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
