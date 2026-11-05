from sqlalchemy import inspect, text

from app.core.database import engine
from app.core.logger import get_logger

logger = get_logger(__name__)

# 本项目未引入 Alembic，这里对已存在的表做幂等列补齐
_NOTES_COLUMNS = {
    "status": "VARCHAR(16) DEFAULT 'pending'",
    "nodes_count": "INTEGER DEFAULT 0",
    "edges_count": "INTEGER DEFAULT 0",
    "error_message": "TEXT",
    "processed_time": "TIMESTAMP",
    # 上传时用户指定的学科（为空则由抽取模型判断）
    "subject": "VARCHAR(32)",
}

# 独特宠物身份字段（注册即生成，存量宠物补生成）
_PETS_COLUMNS = {
    "name": "VARCHAR(32)",
    "species": "VARCHAR(24)",
    "color": "VARCHAR(16)",
    "personality": "VARCHAR(24)",
    "seed": "INTEGER",
    "voice_preset": "VARCHAR(32)",
    "tree_growth_consumed": "FLOAT DEFAULT 0",
    "growth_cycles": "INTEGER DEFAULT 0",
    "total_harvested": "INTEGER DEFAULT 0",
    # 情感状态机字段
    "mood": "VARCHAR(16)",
    "bond": "INTEGER DEFAULT 0",
    "last_interaction": "TIMESTAMP",
    "streak_days": "INTEGER DEFAULT 0",
    "last_active_date": "DATE",
    "last_care_date": "DATE",
}

# 存量宠物补算累计收取果实数：每次收取消耗 100 成长值、产出 3 颗果实。
# 仅在 total_harvested 仍为 0 且存在已消耗成长值时执行，保证幂等。
_PETS_BACKFILL = (
    "UPDATE pets SET total_harvested = CAST(tree_growth_consumed / 100 * 3 AS INTEGER) "
    "WHERE total_harvested = 0 AND tree_growth_consumed > 0"
)

# 社区帖子封面图（用户在发布时上传的内容相关配图）
_COMMUNITY_COLUMNS = {
    "cover_url": "VARCHAR(512)",
}

# 社区评论的二级回复（指向被回复的顶层评论）
_COMMUNITY_COMMENT_COLUMNS = {
    "parent_id": "VARCHAR(36)",
    # 软删除标记：删除自己的评论仅打标，保留行以承载他人回复
    "is_deleted": "BOOLEAN DEFAULT 0",
}

# 用户昵称（可修改，展示名优先于脱敏手机号）
_USERS_COLUMNS = {
    "nickname": "VARCHAR(32)",
}

# 通知的关联对象（点进去看原文）；存量通知为 NULL，不回填
_NOTIFICATIONS_COLUMNS = {
    "target_type": "VARCHAR(16)",
    "target_id": "VARCHAR(36)",
}

# 数字分身头像图（用户自行上传）
_AVATAR_COLUMNS = {
    "avatar_url": "VARCHAR(255)",
}

# 反思记录的评分明细：薄弱点与推荐资源（JSON 数组字符串）
# reason / generated_by：出题依据与是否模板兜底；mastery_*：评分当下的掌握度记账
_REFLECTION_COLUMNS = {
    "weak_points": "TEXT",
    "resources": "TEXT",
    "key_points": "TEXT",
    "reason": "TEXT",
    "generated_by": "VARCHAR(16)",
    "mastery_before": "FLOAT",
    "mastery_after": "FLOAT",
    "mastery_weight": "FLOAT",
}

_TABLE_COLUMNS = {
    "notes": _NOTES_COLUMNS,
    "pets": _PETS_COLUMNS,
    "community_posts": _COMMUNITY_COLUMNS,
    "community_comments": _COMMUNITY_COMMENT_COLUMNS,
    "users": _USERS_COLUMNS,
    "avatars": _AVATAR_COLUMNS,
    "notifications": _NOTIFICATIONS_COLUMNS,
    "reflection_records": _REFLECTION_COLUMNS,
}


async def _existing_columns(conn, table: str) -> set[str]:
    """通过 SQLAlchemy 反射读取现有列，兼容 SQLite / PostgreSQL 等不同方言。"""

    def _read(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        if not inspector.has_table(table):
            return set()
        return {col["name"] for col in inspector.get_columns(table)}

    return await conn.run_sync(_read)


async def _ensure_table_columns(conn, table: str, columns: dict) -> None:
    existing = await _existing_columns(conn, table)
    if not existing:
        # 表尚未创建（全新环境），交由建表流程处理
        return
    for column, ddl in columns.items():
        if column not in existing:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            logger.info("schema migration: %s.%s added", table, column)


async def ensure_schema() -> None:
    try:
        # 导入全部模型，确保其注册到 Base.metadata
        import importlib
        import pkgutil

        import app.models
        from app.models.user import Base

        for module in pkgutil.iter_modules(app.models.__path__):
            importlib.import_module(f"app.models.{module.name}")

        async with engine.begin() as conn:
            # 幂等建表：仅创建尚不存在的表（本项目未引入 Alembic）
            await conn.run_sync(Base.metadata.create_all)
            for table, columns in _TABLE_COLUMNS.items():
                await _ensure_table_columns(conn, table, columns)
            await conn.execute(text(_PETS_BACKFILL))
    except Exception:  # noqa: BLE001
        logger.exception("schema migration failed")
