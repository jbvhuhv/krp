"""回填演示库的掌握度账本，让「掌握度溯源」有据可查。

问题
----
`demo/krp-demo.db` 里的 10 条已答反思记录是演示数据，存在两个毛病：

1. 其中 3 条 `mastery_score` 是 0–1 比例（0.85 / 0.92 / 0.88），
   前端按百分比展示，于是这三条历史记录显示成「1% / 1% / 1%」；
2. 全部没有 `mastery_before / mastery_after / mastery_weight`，
   点开知识点的「掌握度溯源」抽屉，时间线永远是空的——图谱上有掌握度，
   却没有任何一条记录解释它是怎么来的。

做法
----
按应用当前的公式（`compute_mastery_weights`）把每条答题记录重放一遍：

    新掌握度 = 旧掌握度 × 旧权重 + 本次得分 × 新权重

把每一步的「改前 / 改后 / 本次权重」写回记录，并把图谱里对应节点的
`mastery / last_reviewed` 对齐到最后一次答题的结果。比例量纲的记录先 ×100。

这样图谱值与账本互相解释：点开节点 → 时间线里能看到每一次分数怎么把掌握度推上去。

用法
----
    python backend/scripts/backfill_demo_ledger.py            # 只预览
    python backend/scripts/backfill_demo_ledger.py --write    # 落盘（同时改 db 与 jsonl）
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from app.services.reflection_service import compute_mastery_weights  # noqa: E402

DEMO_DB = os.path.join(BACKEND_DIR, "demo", "krp-demo.db")
DEMO_GRAPH = os.path.join(BACKEND_DIR, "demo", "neo4j-demo.jsonl")

LEDGER_COLUMNS = {
    "reason": "TEXT",
    "generated_by": "VARCHAR(16)",
    "mastery_before": "FLOAT",
    "mastery_after": "FLOAT",
    "mastery_weight": "FLOAT",
}


def _ensure_columns(con: sqlite3.Connection) -> None:
    existing = {row[1] for row in con.execute("PRAGMA table_info(reflection_records)")}
    for column, ddl in LEDGER_COLUMNS.items():
        if column not in existing:
            con.execute(f"ALTER TABLE reflection_records ADD COLUMN {column} {ddl}")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _graph_nodes() -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    with open(DEMO_GRAPH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") != "node":
                continue
            props = rec.get("props") or {}
            if props.get("node_type") == "knowledge":
                nodes.setdefault(props.get("name"), props)
    return nodes


def backfill(db_path: str = DEMO_DB, graph_path: str = DEMO_GRAPH) -> dict:
    """重放账本，返回统计信息；不写文件。"""
    by_name = _graph_nodes()
    con = sqlite3.connect(f"file:{db_path.replace(os.sep, '/')}", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT id, target_node_id, node_name, mastery_score, created_at, answered_at
            FROM reflection_records
            WHERE answer IS NOT NULL AND mastery_score IS NOT NULL
            ORDER BY COALESCE(answered_at, created_at) ASC
            """
        ).fetchall()

        scaled = 0
        attached = 0
        updates: list[tuple] = []
        state: dict[str, dict] = {}

        for row in rows:
            score = float(row["mastery_score"])
            # 0–1 比例的旧记录：0.85 表示 85 分
            if score <= 1.0:
                score *= 100.0
                scaled += 1

            node_id = row["target_node_id"]
            if not node_id:
                node = by_name.get(row["node_name"] or "")
                node_id = node.get("id") if node else None
                if node_id:
                    attached += 1
            if not node_id:
                continue

            when = _parse(row["answered_at"]) or _parse(row["created_at"])
            entry = state.get(node_id)
            old = entry["mastery"] if entry else 0.0
            days = None
            if entry and when:
                days = max(0.0, (when - entry["when"]).total_seconds() / 86400.0)
            _, new_weight = compute_mastery_weights(old, days)
            new = old * (1.0 - new_weight) + score * new_weight

            state[node_id] = {"mastery": new, "when": when}
            updates.append(
                (
                    round(old, 2),
                    round(new, 2),
                    round(new_weight, 4),
                    round(score, 2),
                    node_id,
                    row["id"],
                )
            )

        return {
            "records": len(rows),
            "scaled_from_ratio": scaled,
            "attached_nodes": attached,
            "updated": len(updates),
            "nodes": {
                node_id: {"mastery": round(item["mastery"], 2), "last_reviewed": _iso(item["when"])}
                for node_id, item in state.items()
            },
            "updates": updates,
        }
    finally:
        con.close()


def _write_graph(path: str, nodes: dict[str, dict]) -> int:
    out: list[str] = []
    touched = 0
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("kind") == "node":
                props = rec.get("props") or {}
                patch = nodes.get(props.get("id"))
                if patch:
                    props.update(patch)
                    rec["props"] = props
                    touched += 1
            out.append(json.dumps(rec, ensure_ascii=False))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, path)
    return touched


def main() -> None:
    parser = argparse.ArgumentParser(description="回填演示库的掌握度账本")
    parser.add_argument("--write", action="store_true", help="写回 db 与 jsonl（默认只预览）")
    args = parser.parse_args()

    result = backfill()
    print("演示账本回填：")
    for key in ("records", "scaled_from_ratio", "attached_nodes", "updated"):
        print(f"  {key}: {result[key]}")
    for node_id, item in result["nodes"].items():
        print(f"  {node_id}: mastery={item['mastery']} last_reviewed={item['last_reviewed']}")

    if not args.write:
        print("\n（预览模式，未写文件；加 --write 落盘）")
        return

    con = sqlite3.connect(f"file:{DEMO_DB.replace(os.sep, '/')}", uri=True)
    try:
        _ensure_columns(con)
        for before, after, weight, score, node_id, record_id in result["updates"]:
            con.execute(
                """
                UPDATE reflection_records
                SET mastery_score = ?, mastery_before = ?, mastery_after = ?,
                    mastery_weight = ?, target_node_id = COALESCE(target_node_id, ?)
                WHERE id = ?
                """,
                (score, before, after, weight, node_id, record_id),
            )
        con.commit()
    finally:
        con.close()

    touched = _write_graph(DEMO_GRAPH, result["nodes"])
    print(f"\n已写回 {DEMO_DB}（{result['updated']} 条记录）与 {DEMO_GRAPH}（{touched} 个节点）")


if __name__ == "__main__":
    main()
