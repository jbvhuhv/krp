import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager, suppress

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
from app.core.middleware import SecurityHeadersMiddleware, TraceIdMiddleware

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = get_logger(__name__)


async def _recover_graph_backend(driver, interval: float = 60.0) -> None:
    """降级后自愈：定期重探 Neo4j，成功即把图谱后端切回 Neo4j（无需重启进程）。

    场景：宿主机重启时应用可能比 Neo4j 先就绪。启动探测带了重试，但若 Neo4j 启动
    更慢（磁盘慢、数据量大），仍会降级为内置只读图谱 —— 此时由本协程兜底恢复，
    避免「必须手工重启容器才能恢复」。
    """
    from app.services.graph import neo4j_available, set_neo4j_available

    while True:
        await asyncio.sleep(interval)
        if neo4j_available() is not False:
            continue
        try:
            async with driver.session() as session:
                await (await session.run("RETURN 1 AS ok")).single()
        except Exception:  # noqa: BLE001 - 仍不可用就等下一轮，保持静默
            continue
        set_neo4j_available(True)
        logger.warning("Neo4j 已恢复：图谱后端自动切回 Neo4j")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.database import neo4j_driver
    from app.core.demo_bootstrap import bootstrap_neo4j, bootstrap_sqlite
    from app.core.schema_migrations import ensure_schema
    from app.services.graph import init_property_indexes, init_vector_index
    from app.services.note_recovery import recover_stale_notes

    # 必须在建表之前：空库时灌入演示数据（已存在数据则不做任何改动）
    bootstrap_sqlite()
    await ensure_schema()
    await init_vector_index(neo4j_driver)
    # 属性索引：图谱查询几乎都按 (user_id, node_type) 过滤，缺索引时是全标签扫描
    await init_property_indexes(neo4j_driver)
    # 图谱为空时导入演示图谱（首次部署 / 本地首次运行即可看到完整知识图谱）
    await bootstrap_neo4j(neo4j_driver)
    # 探测 Neo4j 可用性：不可用时图谱退回「内置只读演示图谱」，避免整页空白
    from app.services.graph import ping_neo4j

    await ping_neo4j(neo4j_driver)
    # 数据规范化：早期版本把 last_reviewed 写成 ISO 字符串，会让「今日反思」500（幂等）
    from app.core.graph_migrations import normalize_last_reviewed

    await normalize_last_reviewed(neo4j_driver)
    # 抽取任务在进程内执行，服务重启会丢失排队任务；启动时自愈，避免笔记永远停在 pending
    await recover_stale_notes()
    if settings.SCHEDULER_ENABLED:
        from app.scheduler import setup_scheduler

        setup_scheduler()
    # 降级自愈：后台定期重探 Neo4j，恢复后自动切回（覆盖"启动重试窗口内仍未就绪"的情况）
    graph_recovery_task: asyncio.Task | None = None
    if neo4j_driver is not None:
        graph_recovery_task = asyncio.create_task(_recover_graph_backend(neo4j_driver))
    yield
    if graph_recovery_task is not None:
        graph_recovery_task.cancel()
        with suppress(asyncio.CancelledError):
            await graph_recovery_task
    if settings.SCHEDULER_ENABLED:
        from app.scheduler import shutdown_scheduler

        shutdown_scheduler()
    from app.services.providers.base import close_http_client

    await close_http_client()
    await close_db_connections()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.APP_VERSION,
    # 接口文档默认关闭：演示环境常常 DEBUG=true，若不单独控制，/docs 会把完整接口面
    # 公开给公网（含全部端点与参数结构）。本地需要看文档时在 .env 设 ENABLE_API_DOCS=true。
    openapi_url=(
        f"{settings.API_V1_PREFIX}/openapi.json" if settings.ENABLE_API_DOCS else None
    ),
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
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
app.add_middleware(SecurityHeadersMiddleware)

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
async def health(deep: bool = False):
    """健康检查。

    默认只返回进程存活状态；`?deep=1` 时额外探测关系库与 Neo4j ——
    供 UptimeRobot 等保活监控使用（免费容器平台会因闲置休眠）。
    探测失败不返回 5xx：图谱是可选能力，Neo4j 不可用时自动降级为内置只读演示图谱。
    """
    from app.services.graph import neo4j_available

    backend = {True: "neo4j", False: "local"}.get(neo4j_available(), "unknown")
    if not deep:
        return {"status": "ok", "graph_backend": backend}

    checks = {"database": "unknown", "neo4j": "unknown"}
    try:
        from sqlalchemy import text

        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - 依赖外部服务
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        from app.core.database import neo4j_driver

        async with neo4j_driver.session() as session:
            await (await session.run("RETURN 1 AS ok")).single()
        checks["neo4j"] = "ok"
    except Exception as exc:  # pragma: no cover - 依赖外部服务
        checks["neo4j"] = f"error: {type(exc).__name__}"

    dirty = None
    if checks["neo4j"] == "ok":
        try:
            from app.core.database import neo4j_driver
            from app.core.graph_migrations import count_dirty_last_reviewed

            dirty = await count_dirty_last_reviewed(neo4j_driver)
        except Exception:  # pragma: no cover - 统计失败不影响健康判定
            dirty = None

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {
        "status": status,
        **checks,
        "graph_backend": backend,
        "dirty_last_reviewed": dirty,
    }


def _resolve_spa_dir() -> str | None:
    """定位前端构建产物目录（存在 index.html 才算有效）。

    目录关系（以 backend/app/main.py 为基准）：
        backend_dir = 上一级（仓库里是 backend/，容器里是 /app）
        repo_root   = 再上一级（仓库根；容器里没有前端源码，该候选自然落空）
    早期实现把 backend_dir 多退了一级，导致「本地直接 uvicorn 起后端 + 后端托管前端」
    这条路径永远找不到 frontend/dist，所有页面 404（只有容器里碰巧能用）。
    """
    candidates = []
    if settings.FRONTEND_DIST:
        candidates.append(settings.FRONTEND_DIST)
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    repo_root = os.path.abspath(os.path.join(backend_dir, ".."))
    candidates.extend(
        [
            os.path.join(backend_dir, "frontend_dist"),  # 容器内（Dockerfile 拷贝到此处）
            os.path.join(repo_root, "frontend", "dist"),  # 仓库内（前端已 npm run build）
        ]
    )
    for cand in candidates:
        if cand and os.path.isfile(os.path.join(cand, "index.html")):
            return cand
    return None


def _resolve_static_file(root: str, relative: str) -> str | None:
    """把请求路径安全地解析为 root 内的文件；越界（`..`、绝对路径、跨盘符）返回 None。

    安全说明：SPA 回退曾直接 `os.path.join(root, full_path)` + `isfile` 就返回文件，
    而 `{full_path:path}` 会原样接收 `../`（uvicorn 还会把 %2F 解码成 /），
    于是 `/..%2F..%2Fbackend%2F.env`、`/..%2Fkrp.db` 能读走密钥与整个业务库。
    StaticFiles 自带这层校验，手写 handler 必须自己补。
    """
    if not relative or "\x00" in relative:
        return None
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, relative))
    try:
        # commonpath 兼容不同盘符/大小写，比 startswith 可靠（后者会放过 /root-evil）
        if os.path.commonpath([root_real, candidate]) != root_real:
            return None
    except ValueError:  # Windows 跨盘符
        return None
    return candidate if os.path.isfile(candidate) else None


_SPA_DIR = _resolve_spa_dir()
if _SPA_DIR:
    _SPA_ROOT = os.path.realpath(_SPA_DIR)
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
        candidate = _resolve_static_file(_SPA_ROOT, full_path)
        if candidate:
            return FileResponse(candidate)
        return FileResponse(os.path.join(_SPA_ROOT, "index.html"))

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
