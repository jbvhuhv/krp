import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db_connections
from app.core.exceptions import KnowledgeBaseException
from app.core.logger import get_logger, get_trace_id, setup_logging
from app.core.middleware import TraceIdMiddleware

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.database import neo4j_driver
    from app.core.schema_migrations import ensure_schema
    from app.services.graph import init_vector_index

    await ensure_schema()
    await init_vector_index(neo4j_driver)
    if settings.SCHEDULER_ENABLED:
        from app.scheduler import setup_scheduler

        setup_scheduler()
    yield
    if settings.SCHEDULER_ENABLED:
        from app.scheduler import shutdown_scheduler

        shutdown_scheduler()
    from app.services.providers.base import close_http_client

    await close_http_client()
    await close_db_connections()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TraceIdMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
# 仅公开封面 / 头像目录；用户上传的原始笔记文件存放在 UPLOAD_DIR/notes 下，不对外静态暴露
for _public_sub in ("covers", "avatars"):
    _public_dir = os.path.join(settings.UPLOAD_DIR, _public_sub)
    os.makedirs(_public_dir, exist_ok=True)
    app.mount(
        f"/uploads/{_public_sub}",
        StaticFiles(directory=_public_dir),
        name=f"uploads_{_public_sub}",
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


def _trace_id_of(request: Request) -> str:
    return getattr(request.state, "trace_id", None) or get_trace_id()


def _error_content(code: int, message: str, detail, request: Request) -> dict:
    return {
        "code": code,
        "message": message,
        "detail": detail,
        "trace_id": _trace_id_of(request),
    }


@app.exception_handler(KnowledgeBaseException)
async def knowledge_base_exception_handler(request: Request, exc: KnowledgeBaseException):
    logger.warning("business exception: %s", exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_content(exc.code, exc.message, exc.detail, request),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else "请求处理失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_content(exc.status_code, message, detail, request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("validation error: %s", exc.errors())
    return JSONResponse(
        status_code=422,
        content=_error_content(
            422, "请求参数校验失败", jsonable_encoder(exc.errors()), request
        ),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from neo4j.exceptions import ServiceUnavailable

    if isinstance(exc, ServiceUnavailable):
        logger.error("neo4j unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content=_error_content(503, "知识图谱服务不可用，请启动 Neo4j", None, request),
        )

    logger.error("unhandled exception: %s", exc, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_error_content(500, "内部服务器错误", None, request),
    )
