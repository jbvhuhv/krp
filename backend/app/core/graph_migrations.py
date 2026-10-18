"""Neo4j 图谱数据规范化迁移（幂等）。

背景：早期版本曾把 ``last_reviewed`` 以 ISO 字符串写入图谱。Neo4j 属性是动态类型，
字符串能正常入库，但 ``duration.between(n.last_reviewed, datetime())`` 只接受时间类型，
一旦命中脏数据就会抛 ``Neo.ClientError.Procedure.ProcedureCallFailed``，
导致「今日反思」接口整页 500。

本模块在启动时做一次性、幂等的类型规整：
  - 只处理 ``valueType(...) STARTS WITH 'STRING'`` 的节点，正常数据不受影响
  - 重复执行结果一致（第二次起 fixed 恒为 0）
  - 任何异常只记录日志，不阻断服务启动
"""

from app.core.logger import get_logger

logger = get_logger(__name__)

# 注意：Neo4j 5.26 的 valueType() 返回 GQL 风格类型名（如 "STRING NOT NULL"），
# 因此只能用 STARTS WITH 'STRING' 判断，不能用等值比较。
_NORMALIZE_LAST_REVIEWED = """
MATCH (n:KnowledgeNode)
WHERE n.last_reviewed IS NOT NULL
  AND valueType(n.last_reviewed) STARTS WITH 'STRING'
SET n.last_reviewed = datetime(n.last_reviewed)
RETURN count(n) AS fixed
"""

_COUNT_DIRTY_LAST_REVIEWED = """
MATCH (n:KnowledgeNode)
WHERE n.last_reviewed IS NOT NULL
  AND valueType(n.last_reviewed) STARTS WITH 'STRING'
RETURN count(n) AS dirty
"""


async def normalize_last_reviewed(driver) -> int:
    """把字符串类型的 last_reviewed 转换为 Neo4j 时间类型，返回修复条数。"""
    if driver is None:
        return 0
    try:
        async with driver.session() as session:
            result = await session.run(_NORMALIZE_LAST_REVIEWED)
            record = await result.single()
            fixed = int(record["fixed"]) if record else 0
    except Exception:  # noqa: BLE001 - 迁移失败不应阻断启动
        logger.exception("graph migration: last_reviewed 规范化失败（已跳过）")
        return 0
    if fixed:
        logger.warning(
            "graph migration: 已修复 %d 条 last_reviewed 字符串类型数据", fixed
        )
    return fixed


async def count_dirty_last_reviewed(driver) -> int:
    """统计仍为字符串类型的 last_reviewed 数量，供健康检查使用。"""
    if driver is None:
        return 0
    async with driver.session() as session:
        result = await session.run(_COUNT_DIRTY_LAST_REVIEWED)
        record = await result.single()
        return int(record["dirty"]) if record else 0
