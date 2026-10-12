from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_postgres_url, settings

engine = create_async_engine(get_postgres_url(), echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

neo4j_driver = AsyncGraphDatabase.driver(
    settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
)

redis_client = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD or None,
    decode_responses=True,
    socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
    socket_timeout=settings.REDIS_CONNECT_TIMEOUT,
    health_check_interval=30,
    retry=Retry(NoBackoff(), 0),
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def close_db_connections() -> None:
    await engine.dispose()
    await neo4j_driver.close()
    await redis_client.close()
