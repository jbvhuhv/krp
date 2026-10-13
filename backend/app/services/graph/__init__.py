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


async def ping_neo4j(driver: AsyncDriver | None) -> bool:
    """探测 Neo4j 是否可用（启动时调用一次，结果缓存供依赖注入判断）。

    不可用时不抛异常：应用会退回「内置只读演示图谱」（见 local_service.py），
    使没有 Neo4j 的环境（免费云部署、评委本地仅跑 SQLite）里知识图谱页依然有内容。
    """
    if driver is None:
        set_neo4j_available(False)
        return False
    try:
        async with driver.session() as session:
            await (await session.run("RETURN 1 AS ok")).single()
        set_neo4j_available(True)
        return True
    except Exception:
        logger.warning(
            "Neo4j 不可用：知识图谱将使用内置只读演示数据（配置 NEO4J_URI 可启用完整功能）"
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


class GraphService(CrudMixin, TreeMixin, VectorMixin, StatsMixin):
    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def ensure_vector_index(
        self, dimension: int, index_name: str = DEFAULT_VECTOR_INDEX
    ) -> None:
        await init_vector_index(self.driver, dimension, index_name)
