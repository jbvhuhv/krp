import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
    from app.core.demo_bootstrap import bootstrap_neo4j, bootstrap_sqlite
    from app.core.schema_migrations import ensure_schema
    from app.services.graph import init_vector_index
    from app.services.note_recovery import recover_stale_notes

    # 必须在建表之前：空库时灌入演示数据（已存在数据则不做任何改动）
    bootstrap_sqlite()
    await ensure_schema()
    await init_vector_index(neo4j_driver)
    # 图谱为空时导入演示图谱（Render 首次部署 / 本地首次运行即可看到完整知识图谱）
    await bootstrap_neo4j(neo4j_driver)
    # 抽取任务在进程内执行，服务重启会丢失排队任务；启动时自愈，避免笔记永远停在 pending
    await recover_stale_notes()
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


def _resolve_spa_dir() -> str | None:
    """定位前端构建产物目录（存在 index.html 才算有效）。"""
    candidates = []
    if settings.FRONTEND_DIST:
        candidates.append(settings.FRONTEND_DIST)
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidates.extend(
        [
            os.path.join(backend_dir, "frontend_dist"),  # 容器内（Dockerfile 拷贝到此处）
            os.path.abspath(os.path.join(backend_dir, "..", "frontend", "dist")),  # 仓库内
        ]
    )
    for cand in candidates:
        if cand and os.path.isfile(os.path.join(cand, "index.html")):
            return cand
    return None


_SPA_DIR = _resolve_spa_dir()
if _SPA_DIR:
    _assets_dir = os.path.join(_SPA_DIR, "assets")
    if os.path.isdir(_assets_dir):
        # 带哈希的静态资源可长缓存
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="spa_assets")

    _API_PREFIX = settings.API_V1_PREFIX.strip("/")
    _RESERVED = {"docs", "redoc", "openapi.json", "health"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """SPA 前端路由回退：非 API 路径统一返回 index.html。

        由后端直接托管前端，可实现单服务部署（前后端同源，无需 CORS）。
        """
        if full_path in _RESERVED or full_path.startswith(_API_PREFIX) or full_path.startswith("uploads/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = os.path.join(_SPA_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_SPA_DIR, "index.html"))

    logger.info("已启用前端静态托管：%s", _SPA_DIR)


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
