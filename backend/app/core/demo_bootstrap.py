"""演示数据自动引导（Demo Bootstrap）。

目标：让"克隆即可运行、部署即有内容"成立 —— 当数据库或图谱为空时，自动灌入
随仓库分发的演示数据（`backend/demo/`），避免任何人打开应用只看到满屏"暂无数据"。

  - SQLite：目标库不存在或没有 users 数据时，复制 `demo/krp-demo.db`
  - Neo4j ：图谱为空时，导入 `demo/neo4j-demo.jsonl`（MERGE 幂等）

特性：
  - **幂等且只读判断**：已有数据时绝不做任何改动
  - **异常隔离**：Neo4j 不可达、文件缺失等任何异常都只记日志，绝不影响服务启动
  - **可关闭**：`DEMO_BOOTSTRAP=false`；pytest 环境下自动跳过
  - 演示库已脱敏：手机号统一替换、全部内容归到演示账号（见 docs 部署说明）
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEMO_DIR = os.path.join(BACKEND_DIR, "demo")
DEMO_DB = os.path.join(DEMO_DIR, "krp-demo.db")
DEMO_GRAPH = os.path.join(DEMO_DIR, "neo4j-demo.jsonl")

NODE_LABEL = "KnowledgeNode"
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _enabled() -> bool:
    if not settings.DEMO_BOOTSTRAP:
        return False
    # 测试环境跳过：用例自带独立数据库，不应被演示数据干扰
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return False
    return True


def sqlite_target_path() -> str | None:
    """从 POSTGRES_URL 解析出 SQLite 文件绝对路径；非 SQLite 配置返回 None。"""
    url = (settings.POSTGRES_URL or "").strip()
    if not url.startswith("sqlite"):
        return None
    _, _, path = url.partition(":///")
    path = (path or "").strip()
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.abspath(os.path.join(os.getcwd(), path))
    return path


def _db_has_data(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        con = sqlite3.connect(f"file:{path.replace(os.sep, '/')}?mode=ro", uri=True)
        try:
            return con.execute("select count(*) from users").fetchone()[0] > 0
        finally:
            con.close()
    except Exception:
        # 表不存在/文件损坏 → 视为空库
        return False


def bootstrap_sqlite() -> bool:
    """目标 SQLite 为空时复制演示库；返回是否发生引导。

    必须在 `ensure_schema()` **之前**调用（此时尚未建立连接，可安全替换文件）。
    任何异常只记日志，绝不影响服务启动。
    """
    try:
        if not _enabled() or not os.path.isfile(DEMO_DB):
            return False
        target = sqlite_target_path()
        if not target or _db_has_data(target):
            return False
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        shutil.copyfile(DEMO_DB, target)
        logger.info(
            "演示数据引导：数据库为空，已灌入演示数据 → %s（含演示账号，见 docs 部署说明）",
            target,
        )
        return True
    except Exception:
        logger.warning("演示数据引导（SQLite）失败，已跳过", exc_info=True)
        return False


def _load_dump() -> tuple[list[dict], dict[str, list[dict]]]:
    """读取演示图谱 JSONL，返回（节点列表, {关系类型: 关系列表}）。"""
    nodes: list[dict] = []
    edges_by_type: dict[str, list[dict]] = {}
    if not os.path.isfile(DEMO_GRAPH):
        return nodes, edges_by_type
    with open(DEMO_GRAPH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") == "node":
                props = rec.get("props") or {}
                if props.get("id"):
                    nodes.append({"id": props["id"], "props": props})
            elif rec.get("kind") == "edge":
                rel = rec.get("type") or "RELATED_TO"
                if _IDENT_RE.match(rel) and rec.get("src") and rec.get("dst"):
                    edges_by_type.setdefault(rel, []).append(
                        {"src": rec["src"], "dst": rec["dst"], "props": rec.get("props") or {}}
                    )
    return nodes, edges_by_type


async def bootstrap_neo4j(driver, database: str | None = None) -> bool:
    """图谱为空时导入演示图谱（MERGE 幂等）；返回是否发生引导。

    `database` 仅用于测试指向临时库，生产传 None（走默认库）。
    Neo4j 不可达等异常一律吞掉并记日志 —— 图谱是可选能力，不能因此让服务起不来。
    """
    try:
        if not _enabled() or driver is None or not os.path.isfile(DEMO_GRAPH):
            return False

        nodes, edges_by_type = _load_dump()
        if not nodes:
            return False

        async with driver.session(database=database) as session:
            result = await session.run(f"MATCH (n:{NODE_LABEL}) RETURN count(n) AS c")
            record = await result.single()
            existing = (record or {}).get("c", 0) if record else 0
            if existing:
                logger.info("演示数据引导：图谱已有 %d 个节点，跳过导入", existing)
                return False

            logger.info(
                "演示数据引导：图谱为空，开始导入演示图谱（节点 %d，关系类型 %d）",
                len(nodes),
                len(edges_by_type),
            )
            for i in range(0, len(nodes), 200):
                batch = nodes[i : i + 200]
                res = await session.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{NODE_LABEL} {{id: row.id}}) "
                    f"SET n += row.props",
                    rows=batch,
                )
                await res.consume()

            for rel_type, rows in edges_by_type.items():
                for i in range(0, len(rows), 200):
                    batch = rows[i : i + 200]
                    res = await session.run(
                        f"UNWIND $rows AS row "
                        f"MATCH (a:{NODE_LABEL} {{id: row.src}}) "
                        f"MATCH (b:{NODE_LABEL} {{id: row.dst}}) "
                        f"MERGE (a)-[r:{rel_type}]->(b) "
                        f"SET r += row.props",
                        rows=batch,
                    )
                    await res.consume()

            rec = await (
                await session.run(f"MATCH (n:{NODE_LABEL}) RETURN count(n) AS c")
            ).single()
            logger.info("演示数据引导：图谱导入完成，当前节点数 %s", (rec or {}).get("c"))
        return True
    except Exception:
        logger.warning("演示数据引导（Neo4j）失败，已跳过（图谱能力降级）", exc_info=True)
        return False
