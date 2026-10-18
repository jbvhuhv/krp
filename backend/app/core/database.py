from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_postgres_url, settings

_DB_URL = get_postgres_url()
_IS_SQLITE = _DB_URL.startswith("sqlite")

engine = create_async_engine(
    _DB_URL,
    echo=False,
    # SQLite 没有网络往返，pre_ping 只会增加开销；网络型数据库保留探活
    pool_pre_ping=not _IS_SQLITE,
    connect_args={"timeout": 15} if _IS_SQLITE else {},
)


if _IS_SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        """SQLite 并发与稳定性优化。

        默认回滚日志模式下读写互斥，后台抽取与接口请求并发时容易报
        "database is locked"；WAL 允许读写并行，busy_timeout 让写操作等待而非立即失败。
        同时把 synchronous 调为 NORMAL，减少 fsync 次数（WAL 下仍然安全）。
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=15000")
        finally:
            cursor.close()


AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

neo4j_driver = AsyncGraphDatabase.driver(
    settings.NEO4J_URI,
    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    # 连接池与超时：Neo4j 抖动时让请求快速失败/排队受控，而不是无限堆积
    max_connection_pool_size=50,
    connection_acquisition_timeout=30.0,
    connection_timeout=15.0,
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
