from neo4j import AsyncDriver

from app.core.config import settings
from app.core.logger import get_logger
from app.services.graph.constants import DEFAULT_VECTOR_INDEX, NODE_LABEL
from app.services.graph.crud import CrudMixin
from app.services.graph.stats import StatsMixin
from app.services.graph.tree import TreeMixin
from app.services.graph.vector import VectorMixin

__all__ = ["GraphService", "init_vector_index"]

logger = get_logger(__name__)


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
