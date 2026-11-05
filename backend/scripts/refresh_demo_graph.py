"""重算演示图谱的掌握度与复习时间（可复现）。

为什么需要这个脚本
------------------
`demo/neo4j-demo.jsonl` 里混了两批量纲不同的数据：

  - `demo-radar-*` / `demo-success-*` 那批是 **0–1 比例**（0.8 表示 80%）；
  - 真实答题写回的是 **0–100 分**。

应用侧（知识画像、出题理由、前端百分比）统一按 0–100 解释，于是 0.8 被读成
0.8 分：555 个知识点里 554 个判为「薄弱」，平均掌握度 0.3%，每日反思的理由
清一色是「掌握度 0 分，低于 60」。这不是算法错，是演示数据量纲错了。

同时还有 525 个知识点 mastery=0 且没有 last_reviewed —— 从笔记抽取后从未复习，
技术上说得通，但整份演示数据因此看不出「学过什么、哪儿薄弱」，画像和复习队列
全都退化成一条直线。

本脚本做三件事（全部基于节点 id 的稳定哈希，可重复执行、结果一致）
------------------------------------------------------------------
1. 量纲归一：0 < mastery <= 1 的遗留节点 ×100；
2. 补复习轨迹：从未复习的知识点按「未复习 / 薄弱 / 基础 / 熟练 / 精通」分层，
   并按学科给出偏移（学得多的学科整体高一些），复习时间与掌握度弱相关；
3. 已有 last_reviewed 的节点一律不动 —— 那是真实答题留下的历史。

用法
----
    python backend/scripts/refresh_demo_graph.py              # 只预览，不改文件
    python backend/scripts/refresh_demo_graph.py --write      # 落盘
    python backend/scripts/refresh_demo_graph.py --anchor 2026-11-05T12:00:00+08:00

`--anchor` 决定「今天」是哪天，复习时间都以它为基准往回推。发布演示数据前跑一次，
评委看到的就是一份「最近一个月正常学习过」的图谱。

注意：这是**演示用的合成快照**，不是某个真实用户的学习记录。掌握度与复习时间由
节点 id 稳定哈希生成（同一份数据每次跑结果一致），README 与 docs 里都写明了这一点，
不要拿它当真实数据对外宣称。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEMO_GRAPH = os.path.join(BACKEND_DIR, "demo", "neo4j-demo.jsonl")

NODE_TYPE_KNOWLEDGE = "knowledge"

# 学科偏移：同一套分层下，学得多的学科整体高一点，画像才不是一盘散沙
SUBJECT_BIAS = {
    "操作系统": 8.0,
    "Python编程": 6.0,
    "机器学习": 5.0,
    "数据结构": 4.0,
    "数据库": 3.0,
    "数据库原理": 3.0,
    "计算机网络": 2.0,
    "人工智能": 2.0,
    "高等数学": 0.0,
    "大学英语": -2.0,
    "产品设计": -4.0,
    "材料力学": -6.0,
    "嵌入式系统": -8.0,
    "其他": -3.0,
}

# (累计占比, 掌握度下限, 掌握度上限, 是否已复习)
# 演示账号的人设：学期中段，库里的知识点大多过了一遍，薄弱和掌握各占一部分，
# 还有三成是「抽出来但还没复习」。全是 0 分或全是高分都不像真人。
BANDS = (
    (0.30, 0.0, 0.0, False),    # 抽取后从未复习
    (0.50, 20.0, 44.0, True),   # 薄弱
    (0.72, 45.0, 65.0, True),   # 基础
    (0.90, 66.0, 79.0, True),   # 熟练
    (1.00, 80.0, 94.0, True),   # 精通
)

# 极少数「刚学过」的知识点：出题时的弱信号（近 3 天有笔记/问答）需要它们
FRESH_RATIO = 0.04


def _unit(node_id: str, salt: str = "") -> float:
    """把节点 id 映射到 [0,1) 的稳定伪随机数（不用 random，保证可复现）。"""
    digest = hashlib.md5(f"{node_id}:{salt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


def _band(node_id: str) -> tuple[float, float, bool]:
    r = _unit(node_id, "band")
    for upper, low, high, reviewed in BANDS:
        if r < upper:
            return low, high, reviewed
    return BANDS[-1][1], BANDS[-1][2], True


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _reviewed_at(node_id: str, mastery: float, anchor: datetime) -> str:
    """复习时间与掌握度弱相关：掌握得越好，通常复习得越近。"""
    if _unit(node_id, "fresh") < FRESH_RATIO:
        days = _unit(node_id, "fresh-day") * 3.0
    else:
        days = (100.0 - mastery) / 2.4 + 10.0 * _unit(node_id, "days")
    days = max(0.2, min(58.0, days))
    hours = _unit(node_id, "hours") * 10.0
    return _iso(anchor - timedelta(days=days, hours=hours))


def _is_ratio_scale(node: dict) -> bool:
    """遗留的比例量纲：来自演示种子笔记，且值落在 (0,1]。"""
    note = str(node.get("source_note_id") or "")
    if not (note.startswith("demo-radar-") or note.startswith("demo-success-")):
        return False
    try:
        mastery = float(node.get("mastery") or 0.0)
    except (TypeError, ValueError):
        return False
    return 0.0 < mastery <= 1.0


def _normalize(node: dict, anchor: datetime) -> dict:
    """返回处理后的节点属性（不做原地修改，便于预览）。"""
    props = dict(node)
    if props.get("node_type") != NODE_TYPE_KNOWLEDGE:
        return props

    # 1) 量纲归一：比例值有明确含义（0.8 = 80 分），折算后按「已复习」处理，
    #    不能掉进下面的分层逻辑被重新覆盖成 0。
    if _is_ratio_scale(props):
        props["mastery"] = round(float(props["mastery"]) * 100, 1)
        if not props.get("last_reviewed"):
            props["last_reviewed"] = _reviewed_at(props["id"], props["mastery"], anchor)
        return props

    # 2) 真实答题留下的复习时间：原样保留
    if props.get("last_reviewed"):
        return props

    # 3) 从未复习的节点：补一条可信轨迹
    low, high, reviewed = _band(props["id"])
    if not reviewed:
        props["mastery"] = 0.0
        return props

    mastery = low + (high - low) * _unit(props["id"], "mastery")
    mastery += SUBJECT_BIAS.get(str(props.get("subject") or ""), 0.0)
    mastery = round(max(5.0, min(96.0, mastery)), 1)
    props["mastery"] = mastery
    props["last_reviewed"] = _reviewed_at(props["id"], mastery, anchor)
    return props


def _parse_anchor(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def refresh(path: str = DEMO_GRAPH, anchor: datetime | None = None) -> dict:
    """重算整份演示图谱，返回统计信息；`write=True` 时才落盘。"""
    anchor = anchor or datetime.now(timezone.utc)
    out_lines: list[str] = []
    nodes: list[dict] = []
    converted = 0
    filled = 0

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("kind") != "node":
                out_lines.append(line)  # 关系行保持原样，避免无意义的格式变动
                continue

            props = rec.get("props") or {}
            before = props.get("mastery")
            after = _normalize(props, anchor)
            rec["props"] = after
            nodes.append(after)
            if after.get("mastery") != before and after.get("node_type") == NODE_TYPE_KNOWLEDGE:
                if _is_ratio_scale(props):
                    converted += 1
                if not props.get("last_reviewed") and after.get("last_reviewed"):
                    filled += 1
            out_lines.append(json.dumps(rec, ensure_ascii=False))

    knowledge = [n for n in nodes if n.get("node_type") == NODE_TYPE_KNOWLEDGE]
    values = [float(n.get("mastery") or 0.0) for n in knowledge]
    total = len(values) or 1
    stats = {
        "anchor": anchor.isoformat(),
        "knowledge": len(knowledge),
        "converted_from_ratio": converted,
        "filled_review_history": filled,
        "avg_mastery": round(sum(values) / total, 1),
        "weak": sum(1 for v in values if v < 60),
        "basic": sum(1 for v in values if 60 <= v < 80),
        "proficient": sum(1 for v in values if v >= 80),
        "reviewed_ratio": round(
            sum(1 for n in knowledge if float(n.get("mastery") or 0) > 0 or n.get("last_reviewed"))
            / total
            * 100,
            1,
        ),
        "with_review_date": sum(1 for n in knowledge if n.get("last_reviewed")),
        "subjects": len(Counter(n.get("subject") for n in knowledge)),
    }
    return {"stats": stats, "lines": out_lines}


def main() -> None:
    parser = argparse.ArgumentParser(description="重算演示图谱的掌握度与复习时间")
    parser.add_argument("--write", action="store_true", help="写回 jsonl（默认只预览）")
    parser.add_argument("--anchor", default=None, help="基准时间，默认当前时间")
    args = parser.parse_args()

    result = refresh(DEMO_GRAPH, _parse_anchor(args.anchor))
    stats = result["stats"]
    print("演示图谱掌握度重算：")
    for key in (
        "anchor",
        "knowledge",
        "converted_from_ratio",
        "filled_review_history",
        "avg_mastery",
        "weak",
        "basic",
        "proficient",
        "reviewed_ratio",
        "with_review_date",
        "subjects",
    ):
        print(f"  {key}: {stats[key]}")

    if not args.write:
        print("\n（预览模式，未写文件；加 --write 落盘）")
        return

    tmp = f"{DEMO_GRAPH}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(result["lines"]) + "\n")
    os.replace(tmp, DEMO_GRAPH)
    print(f"\n已写回 {DEMO_GRAPH}")


if __name__ == "__main__":
    main()
