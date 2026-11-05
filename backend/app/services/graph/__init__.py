import asyncio

from neo4j import AsyncDriver

from app.core.config import settings
from app.core.logger import get_logger
from app.services.graph.constants import DEFAULT_VECTOR_INDEX, NODE_LABEL
from app.services.graph.crud import CrudMixin
from app.services.graph.stats import StatsMixin
from app.services.graph.tree import TreeMixin
from app.services.graph.vector import VectorMixin

__all__ = [
    "GraphService",
    "init_vector_index",
    "init_property_indexes",
    "ping_neo4j",
    "set_neo4j_available",
    "neo4j_available",
]

logger = get_logger(__name__)

# Neo4j 可用性（启动时探测一次）：None 表示尚未探测
_neo4j_available: bool | None = None


def set_neo4j_available(value: bool) -> None:
    global _neo4j_available
    _neo4j_available = value


def neo4j_available() -> bool | None:
    return _neo4j_available


async def ping_neo4j(
    driver: AsyncDriver | None,
    attempts: int = 6,
    delay: float = 5.0,
) -> bool:
    """探测 Neo4j 是否可用（启动时调用，带重试，结果缓存供依赖注入判断）。

    为什么需要重试：宿主机重启时 Docker 会同时拉起所有容器，``depends_on`` 只在
    ``docker compose up`` 时生效，因此应用常常比 Neo4j 先就绪。早期实现只探测一次，
    命中这个时间差就会永久降级为「内置只读图谱」，表现为图谱写操作全部 403、
    笔记抽取必然失败，且进程运行期间再不会重连。

    不可用时不抛异常：应用会退回「内置只读演示图谱」（见 local_service.py），
    使没有 Neo4j 的环境（免费云部署、评委本地仅跑 SQLite）里知识图谱页依然有内容。
    """
    if driver is None:
        set_neo4j_available(False)
        return False

    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            async with driver.session() as session:
                await (await session.run("RETURN 1 AS ok")).single()
            set_neo4j_available(True)
            if attempt > 1:
                logger.info("Neo4j 连接成功（第 %d 次探测）", attempt)
            return True
        except Exception as exc:  # noqa: BLE001 - 探测失败要降级，不能阻断启动
            last_exc = exc
            if attempt < attempts:
                logger.warning(
                    "Neo4j 探测失败（%d/%d），%.0f 秒后重试：%s",
                    attempt,
                    attempts,
                    delay,
                    type(exc).__name__,
                )
                await asyncio.sleep(delay)

    logger.warning(
        "Neo4j 不可用（已重试 %d 次）：知识图谱将使用内置只读演示数据"
        "（配置 NEO4J_URI 可启用完整功能）",
        attempts,
        exc_info=last_exc,
    )
    set_neo4j_available(False)
    return False


async def init_vector_index(
    driver: AsyncDriver,
    dimension: int | None = None,
    index_name: str | None = None,
) -> None:
    dimension = dimension or settings.EMBEDDING_DIMENSION
    index_name = index_name or settings.NEO4J_VECTOR_INDEX
    try:
        async with driver.session() as session:
            await session.run(
                f"""
                CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                FOR (n:{NODE_LABEL}) ON (n.embedding)
                OPTIONS {{indexConfig: {{
                    `vector.dimensions`: {int(dimension)},
                    `vector.similarity_function`: 'cosine'
                }}}}
                """
            )
    except Exception:
        logger.warning(
            "创建 Neo4j 向量索引失败（Neo4j 可能未启动），已跳过", exc_info=True
        )


# 属性索引：crud.py 里几乎每条查询都是 MATCH (n {user_id, node_type} ...)，
# 没有属性索引时每次打开图谱都是全标签扫描（Neo4j 只会自动为 id 建索引）。
_PROPERTY_INDEXES = (
    ("knowledge_user_idx", f"(n:{NODE_LABEL}) ON (n.user_id)"),
    ("knowledge_user_type_idx", f"(n:{NODE_LABEL}) ON (n.user_id, n.node_type)"),
    ("knowledge_note_idx", f"(n:{NODE_LABEL}) ON (n.source_note_id)"),
)


async def init_property_indexes(driver: AsyncDriver) -> None:
    """幂等创建属性索引；失败只记日志，不影响启动（与向量索引同样的降级策略）。"""
    for name, target in _PROPERTY_INDEXES:
        try:
            async with driver.session() as session:
                await session.run(
                    f"CREATE INDEX {name} IF NOT EXISTS FOR {target}"
                )
        except Exception:
            logger.warning("创建 Neo4j 属性索引失败 name=%s，已跳过", name, exc_info=True)


class GraphService(CrudMixin, TreeMixin, VectorMixin, StatsMixin):
    #: 支持向量检索（数字分身发布时才有必要回填 embedding）
    supports_vector = True

    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def ensure_vector_index(
        self, dimension: int, index_name: str = DEFAULT_VECTOR_INDEX
    ) -> None:
        await init_vector_index(self.driver, dimension, index_name)
