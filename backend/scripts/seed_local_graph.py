"""把刷新后的演示图谱灌进本机 Neo4j，让知识画像不再是「全员 0 分」。

问题
----
`demo/neo4j-demo.jsonl` 是随仓库分发的演示图谱快照（555 个知识点，平均掌握度 42.4），
但 `demo_bootstrap.bootstrap_neo4j()` 只在**图谱为空**时才导入它。本机开发库里有真实
笔记抽取出来的节点，于是快照永远不会生效：`/api/v1/graph/study-profile` 返回
「平均掌握度 0%、熟练度 0%」，知识花园、复习队列全是一条直线。

更别扭的是：Neo4j 挂掉时降级模式读的正是这份快照（`local_service.py`），所以
「降级」看到的数据反而比「连上」好看。

做法
----
1. 按手机号在 SQLite 里找到目标用户，把快照里所有节点的 `user_id` 改写成它
   （快照原本属于 demo 用户，与演示号对不上）；
2. `MERGE` 导入，按节点 id 幂等，可重复执行；
3. `--replace` 先删该用户现有图谱，得到一份「干净」的演示状态（推荐路演前用）；
4. 指向本地不存在的笔记的 `source_note_id` 置空，避免前端「查看来源」404；
5. `last_reviewed` 直接写成 Neo4j datetime，省掉启动期那趟字符串规范化。

用法
----
    python backend/scripts/seed_local_graph.py                       # 只预览，不写库
    python backend/scripts/seed_local_graph.py --write               # 合并导入
    python backend/scripts/seed_local_graph.py --write --replace     # 先清空该用户图谱
    python backend/scripts/seed_local_graph.py --phone 13900000001   # 指定目标用户
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings  # noqa: E402

DEMO_GRAPH = os.path.join(BACKEND_DIR, "demo", "neo4j-demo.jsonl")
DEFAULT_PHONE = "13900000001"
BATCH = 200
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sqlite_path() -> str:
    """从 settings.POSTGRES_URL 解析出 SQLite 文件路径（本脚本只支持本地开发库）。"""
    url = settings.POSTGRES_URL or ""
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        raise SystemExit(
            f"[ERROR] 当前关系库不是 SQLite（{url}）。本脚本用于本地开发环境，"
            "远程库请自行用 Cypher 导入。"
        )
    raw = url[len(prefix) :]
    if raw.startswith("./"):
        return os.path.join(BACKEND_DIR, raw[2:])
    return raw if os.path.isabs(raw) else os.path.join(BACKEND_DIR, raw)


def _resolve_user(phone: str) -> tuple[str, str]:
    db = _sqlite_path()
    if not os.path.isfile(db):
        raise SystemExit(f"[ERROR] 找不到关系库文件：{db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT id, phone FROM users WHERE phone = ?", (phone,)).fetchone()
        if not row:
            raise SystemExit(f"[ERROR] 关系库里没有手机号 {phone} 的用户，请先登录一次建号。")
        note_ids = {r[0] for r in con.execute("SELECT id FROM notes")}
        return row[0], note_ids
    finally:
        con.close()


def _load_dump(note_ids: set[str]) -> tuple[list[dict], dict[str, list[dict]], int]:
    nodes: list[dict] = []
    edges: dict[str, list[dict]] = {}
    cleared = 0
    with open(DEMO_GRAPH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") == "node":
                props = dict(rec.get("props") or {})
                src_note = props.get("source_note_id")
                if src_note and src_note not in note_ids:
                    props["source_note_id"] = None
                    cleared += 1
                reviewed = props.get("last_reviewed")
                if isinstance(reviewed, str):
                    try:
                        props["last_reviewed"] = datetime.fromisoformat(reviewed)
                    except ValueError:
                        props["last_reviewed"] = None
                nodes.append({"labels": rec.get("labels") or ["KnowledgeNode"], "props": props})
            elif rec.get("kind") == "edge":
                rel = rec.get("type") or "RELATED_TO"
                if not _IDENT.match(rel) or not rec.get("src") or not rec.get("dst"):
                    continue
                edges.setdefault(rel, []).append(
                    {"src": rec["src"], "dst": rec["dst"], "props": rec.get("props") or {}}
                )
    return nodes, edges, cleared


async def _seed(phone: str, write: bool, replace: bool) -> None:
    from neo4j import AsyncGraphDatabase

    uid, note_ids = _resolve_user(phone)
    nodes, edges, cleared = _load_dump(note_ids)
    for item in nodes:
        item["props"]["user_id"] = uid

    knowledge = [n for n in nodes if n["props"].get("node_type") == "knowledge"]
    mastery = [n["props"].get("mastery") or 0 for n in knowledge]
    avg = sum(mastery) / len(mastery) if mastery else 0

    print(f"[i] 目标用户 : {phone} -> {uid}")
    print(f"[i] 关系库   : {_sqlite_path()}")
    print(f"[i] 快照     : 节点 {len(nodes)}（知识点 {len(knowledge)}），关系类型 {len(edges)}")
    print(f"[i] 快照掌握度：平均 {avg:.1f}（0–100 制）")
    if cleared:
        print(f"[i] 有 {cleared} 个节点的来源笔记不在本地库，source_note_id 将被置空")

    if not write:
        print("[dry-run] 未写库。加 --write 才会导入；加 --replace 会先清空该用户图谱。")
        return

    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        if settings.NEO4J_PASSWORD
        else None,
    )
    try:
        async with driver.session() as session:
            await (await session.run("RETURN 1 AS ok")).single()

            if replace:
                res = await session.run(
                    "MATCH (n:KnowledgeNode {user_id: $uid}) DETACH DELETE n RETURN count(n) AS c",
                    uid=uid,
                )
                deleted = (await res.single())["c"]
                print(f"[i] --replace：已删除该用户原有节点 {deleted} 个")

            for i in range(0, len(nodes), BATCH):
                batch = nodes[i : i + BATCH]
                await (
                    await session.run(
                        "UNWIND $rows AS row "
                        "MERGE (n:KnowledgeNode {id: row.props.id}) "
                        "SET n += row.props",
                        rows=batch,
                    )
                ).consume()

            for rel, rows in edges.items():
                for i in range(0, len(rows), BATCH):
                    batch = rows[i : i + BATCH]
                    await (
                        await session.run(
                            f"UNWIND $rows AS row "
                            f"MATCH (a:KnowledgeNode {{id: row.src}}) "
                            f"MATCH (b:KnowledgeNode {{id: row.dst}}) "
                            f"MERGE (a)-[r:{rel}]->(b) "
                            f"SET r += row.props",
                            rows=batch,
                        )
                    ).consume()

            stat = (
                await (
                    await session.run(
                        "MATCH (n:KnowledgeNode {user_id: $uid}) "
                        "RETURN count(n) AS total, "
                        "avg(n.mastery) AS avg_mastery, "
                        "sum(CASE WHEN n.last_reviewed IS NULL THEN 1 ELSE 0 END) AS never",
                        uid=uid,
                    )
                ).single()
            ).data()
            print(
                f"[OK] 导入完成：该用户现有节点 {stat['total']} 个，"
                f"平均掌握度 {(stat['avg_mastery'] or 0):.1f}，未复习 {stat['never']} 个"
            )
            print("[i] 刷新前端即可看到知识画像/复习队列的变化。")
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="把演示图谱快照灌进本机 Neo4j")
    parser.add_argument("--phone", default=DEFAULT_PHONE, help="目标用户手机号")
    parser.add_argument("--write", action="store_true", help="真正写库（默认只预览）")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="导入前删除该用户现有图谱，得到干净的演示状态",
    )
    args = parser.parse_args()
    asyncio.run(_seed(args.phone, args.write, args.replace))


if __name__ == "__main__":
    main()
