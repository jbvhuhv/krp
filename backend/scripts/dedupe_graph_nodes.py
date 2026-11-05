"""合并同一笔记内重复的知识点/目录节点。

背景：抽取入库过去是「模型给几条就建几个节点」，同一份笔记里同一个概念
被模型在多个章节重复列出时（实测「进程」×10、「死锁」目录 ×10），
图谱里就出现一排同名节点，导致知识点数虚高、分身的引用来源重复。

现在入库侧已经按 (节点类型, 名称) 去重（crud.write_extraction_result），
这个脚本负责清理历史数据。

规则：
  - 只在**同一用户 + 同一来源笔记 + 同一节点类型 + 同一名称**内合并，
    不同笔记里同名概念（不同课程都讲「硬度」）保持独立，不误合；
  - 保留 mastery 最高的那个，其次 sort_order 最小的（结构上更靠前）；
  - 被删目录的子节点重新挂到保留节点下，不留孤儿；
  - 合并后重算 notes.nodes_count，避免书架/宠物继续用虚高的旧计数。

默认干跑，加 --write 才真正写入。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from neo4j import GraphDatabase  # noqa: E402

NODE_LABEL = "KnowledgeNode"
MERGE_TYPES = ("knowledge", "category")


def _pick_keeper(nodes: list[dict]) -> dict:
    """保留节点：掌握度最高的优先（别把答题记录丢了），其次最早出现的。"""
    return sorted(
        nodes,
        key=lambda n: (
            -(n.get("mastery") or 0.0),
            n.get("sort_order") if n.get("sort_order") is not None else 10**9,
            n.get("id") or "",
        ),
    )[0]


def _find_duplicates(session, uid: str) -> dict[tuple, list[dict]]:
    rows = session.run(
        f"""
        MATCH (n:{NODE_LABEL} {{user_id: $uid}})
        WHERE n.node_type IN $types AND n.source_note_id IS NOT NULL
        RETURN n.id AS id, n.name AS name, n.node_type AS node_type,
               n.source_note_id AS nid, n.parent_id AS parent_id,
               n.mastery AS mastery, n.sort_order AS sort_order
        """,
        uid=uid,
        types=list(MERGE_TYPES),
    ).data()

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["nid"], r["node_type"], r["name"])].append(r)
    return {k: v for k, v in groups.items() if len(v) > 1}


def _merge_group(session, uid: str, key: tuple, nodes: list[dict], write: bool) -> int:
    nid, node_type, name = key
    keeper = _pick_keeper(nodes)
    dupes = [n for n in nodes if n["id"] != keeper["id"]]
    if not dupes:
        return 0

    best_mastery = max((n.get("mastery") or 0.0) for n in nodes)
    dupe_ids = [n["id"] for n in dupes]

    if write:
        # 被删目录的子节点改挂到保留节点，避免结构塌成孤儿
        if node_type == "category":
            session.run(
                f"""
                MATCH (child:{NODE_LABEL} {{user_id: $uid}})
                WHERE child.parent_id IN $dupe_ids
                SET child.parent_id = $keeper_id
                """,
                uid=uid,
                dupe_ids=dupe_ids,
                keeper_id=keeper["id"],
            )
        if best_mastery > (keeper.get("mastery") or 0.0):
            session.run(
                f"MATCH (k:{NODE_LABEL} {{id: $kid}}) SET k.mastery = $m",
                kid=keeper["id"],
                m=best_mastery,
            )
        session.run(
            f"MATCH (n:{NODE_LABEL}) WHERE n.id IN $ids DETACH DELETE n",
            ids=dupe_ids,
        )

    print(
        f"  [{node_type}] {name} ×{len(nodes)} → 1"
        f"（保留 {keeper['id'][:8]}，删除 {len(dupes)} 个）"
    )
    return len(dupes)


def _recount_notes(db_path: str, uid_to_phone: dict[str, str], session, write: bool) -> int:
    """按图谱实际节点数重算 notes.nodes_count（含书根，与抽取口径一致）。"""
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    fixed = 0
    for uid in uid_to_phone:
        rows = session.run(
            f"""
            MATCH (n:{NODE_LABEL} {{user_id: $uid}})
            WHERE n.source_note_id IS NOT NULL
            RETURN n.source_note_id AS nid, count(*) AS c
            """,
            uid=uid,
        ).data()
        actual = {r["nid"]: r["c"] for r in rows}
        for note_id, nodes_count in cur.execute(
            "SELECT id, COALESCE(nodes_count, 0) FROM notes WHERE user_id = ? AND status = 'success'",
            (uid,),
        ).fetchall():
            real = actual.get(note_id)
            if real is None or real == nodes_count:
                continue
            print(
                f"  notes.nodes_count {note_id[:8]} {nodes_count} → {real}"
                f"（{uid_to_phone[uid]}）"
            )
            if write:
                cur.execute("UPDATE notes SET nodes_count = ? WHERE id = ?", (real, note_id))
            fixed += 1
    if write:
        con.commit()
    con.close()
    return fixed


def main() -> int:
    parser = argparse.ArgumentParser(description="合并同一笔记内的重复图谱节点")
    parser.add_argument("--write", action="store_true", help="真正写入（默认只统计）")
    parser.add_argument(
        "--db",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "krp.db"
        ),
    )
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    users = con.execute("SELECT id, phone FROM users").fetchall()
    con.close()

    drv = GraphDatabase.driver(args.uri)
    total_removed = 0
    with drv.session() as session:
        for uid, phone in users:
            print(f"\n用户 {phone or uid[:8]}")
            groups = _find_duplicates(session, uid)
            if not groups:
                print("  无重复节点")
                continue
            for key, nodes in groups.items():
                total_removed += _merge_group(session, uid, key, nodes, args.write)

        print("\n重算笔记知识点数：")
        fixed = _recount_notes(args.db, dict(users), session, args.write)

    drv.close()
    mode = "已写入" if args.write else "干跑（未改动，加 --write 才执行）"
    print(
        f"\n汇总：{'合并' if args.write else '将合并'} {total_removed} 个重复节点，"
        f"{'修正' if args.write else '将修正'} {fixed} 条笔记计数 —— {mode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
