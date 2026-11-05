"""把演示账号的书架从「测试文件名堆」重整成教材式的 11 本书。

问题
----
演示图谱是从一个长期被 E2E / 并发测试污染的本地库导出的，书本节点名直接沿用了
上传文件名，于是「我的书架」显示的是：

    测试图片笔记.png × 5、演示-机器学习基础.md × 5、操作系统要点.md × 4、
    1.docx、2全额、E2E-回归测试.md、E2E-最终回归.md、屏幕截图 2026-10-08 230713.png

33 本书里只有 10 本左右是正常教材名，其余都是测试残留，且同名重复。

第二个问题更隐蔽：快照里 334 个知识点带 `source_note_id`，但关系库里并不存在这些
笔记（`seed_local_graph.py` 会把它置空避免 404），结果是「笔记 1 条 / 书架 33 本 /
每个知识点的来源都是空」——三个页面互相矛盾。

做法
----
1. 按学科把书归组（`人工智能` 并入 `机器学习`、`数据库原理`/`数据结构与算法` 各并入
   对应学科），同组只留一本主书，其余书的子节点用 `CHILD_OF` 重挂到主书后删除；
2. 主书重命名为教材式书名（`操作系统要点.md` → `操作系统 · 进程与内存管理`）；
3. 每本书生成一个**稳定的 UUID**（`uuid5`，重复执行不变）作为 `source_note_id`，
   并把该书子树内所有节点统一指向它，替换掉 `demo-radar-*` 这类假 id；
4. 在关系库里补齐对应笔记记录，使「查看来源」有真实落点，笔记数与书本数一致。

用法
----
    python backend/scripts/reshape_demo_books.py                      # 只预览
    python backend/scripts/reshape_demo_books.py --write              # 执行
    python backend/scripts/reshape_demo_books.py --write --phone 13900000001
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings  # noqa: E402

DEFAULT_PHONE = "13900000001"
NOTE_NAMESPACE = uuid.UUID("6f1a9c2d-3b4e-4f5a-8c7d-0e1f2a3b4c5d")

# 学科别名：左值并入右值，避免「人工智能」与「机器学习」各占一本书
SUBJECT_ALIAS = {
    "人工智能": "机器学习",
    "数据库原理": "数据库",
    "数据结构与算法": "数据结构",
}

# 学科 -> 教材式书名。未列出的学科保持原名、不参与合并（避免误伤真实笔记）
TITLE_BY_SUBJECT = {
    "操作系统": "操作系统 · 进程与内存管理",
    "机器学习": "机器学习基础",
    "计算机网络": "计算机网络",
    "数据结构": "数据结构与算法",
    "数据库": "数据库原理",
    "材料科学与工程": "材料力学基础",
    "材料力学": "材料力学基础",
    "高等数学": "高等数学 · 微积分",
    "大学英语": "大学英语 · 语法要点",
    "嵌入式系统": "嵌入式系统设计",
    "Python编程": "Python 编程入门",
    "产品设计": "产品设计方法",
}

# 没有任何学科、也没有来源笔记的知识点统一收进这本书
FALLBACK_TITLE = "跨学科 · 综合笔记"
UNCLASSIFIED_SUBJECTS = {"其他", ""}


def _sqlite_path() -> str:
    url = settings.POSTGRES_URL or ""
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        raise SystemExit(f"[ERROR] 当前关系库不是 SQLite（{url}），本脚本仅用于本地开发环境。")
    raw = url[len(prefix) :]
    if raw.startswith("./"):
        return os.path.join(BACKEND_DIR, raw[2:])
    return raw if os.path.isabs(raw) else os.path.join(BACKEND_DIR, raw)


def _resolve_user(phone: str) -> str:
    db = _sqlite_path()
    if not os.path.isfile(db):
        raise SystemExit(f"[ERROR] 找不到关系库文件：{db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
    finally:
        con.close()
    if not row:
        raise SystemExit(f"[ERROR] 关系库里没有手机号 {phone} 的用户，请先登录一次建号。")
    return row[0]


def note_id_for(title: str) -> str:
    """书名 -> 稳定笔记 id（重复执行不会变，便于幂等）。"""
    return str(uuid.uuid5(NOTE_NAMESPACE, f"demo-note::{title}"))


async def _collect(driver, uid: str) -> list[dict]:
    async with driver.session() as s:
        res = await s.run(
            """
            MATCH (b:KnowledgeNode {node_type:'book', user_id:$u})
            OPTIONAL MATCH (c:KnowledgeNode)-[:CHILD_OF]->(b)
            RETURN b.id AS id, b.name AS name, b.subject AS subject,
                   b.source_note_id AS source_note_id, count(c) AS kids
            ORDER BY b.name
            """,
            u=uid,
        )
        return [r.data() async for r in res]


def _plan(books: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """返回 (合并组, 待删除的空书, 保留原样的书)。"""
    groups: dict[str, list[dict]] = {}
    keep: list[dict] = []
    drop: list[dict] = []

    for b in books:
        subject = b.get("subject")
        norm = SUBJECT_ALIAS.get(subject, subject) if subject else None
        title = TITLE_BY_SUBJECT.get(norm) if norm else None
        if not title:
            # 未映射的学科：不动，避免把真实笔记也改名
            if not b["kids"]:
                drop.append(b)
            else:
                keep.append(b)
            continue
        groups.setdefault(title, []).append(b)

    planned = []
    for title, members in groups.items():
        members.sort(key=lambda x: (-x["kids"], str(x.get("source_note_id") or "")))
        main = members[0]
        planned.append({"title": title, "main": main, "others": members[1:]})
    return planned, drop, keep


async def _counts(driver, node_id: str) -> tuple[int, int]:
    """主书子树内的知识点数与关系数。"""
    async with driver.session() as s:
        res = await s.run(
            """
            MATCH (k:KnowledgeNode {node_type:'knowledge'})-[:CHILD_OF*1..6]->(:KnowledgeNode {id:$i})
            WITH DISTINCT k
            OPTIONAL MATCH (k)-[rel:RELATED_TO]-(:KnowledgeNode)
            RETURN count(DISTINCT k) AS nodes, count(DISTINCT rel) AS edges
            """,
            i=node_id,
        )
        row = await res.single()
        return (row["nodes"], row["edges"]) if row else (0, 0)


async def _apply(driver, uid: str, plan: list[dict], drop: list[dict]) -> list[dict]:
    """执行合并；返回需要写入关系库的笔记信息。"""
    notes = []
    async with driver.session() as s:
        for p in plan:
            main, title = p["main"], p["title"]
            note_id = note_id_for(title)

            # 先把重复书的子节点重挂到主书，再删掉重复书本身
            for old in p["others"]:
                await (
                    await s.run(
                        """
                    MATCH (c:KnowledgeNode)-[r:CHILD_OF]->(:KnowledgeNode {id:$old})
                    MATCH (main:KnowledgeNode {id:$new})
                    MERGE (c)-[:CHILD_OF]->(main)
                    SET c.parent_id = $new
                    DELETE r
                        """,
                        old=old["id"],
                        new=main["id"],
                    )
                ).consume()
                await (
                    await s.run("MATCH (b:KnowledgeNode {id:$i}) DETACH DELETE b", i=old["id"])
                ).consume()

            await (
                await s.run(
                    "MATCH (b:KnowledgeNode {id:$i}) SET b.name=$n, b.source_note_id=$s",
                    i=main["id"],
                    n=title,
                    s=note_id,
                )
            ).consume()

            # 统一子树来源，替换 demo-radar-* / demo-success-* 这类假 id
            await (
                await s.run(
                    """
                    MATCH (k:KnowledgeNode)-[:CHILD_OF*1..6]->(:KnowledgeNode {id:$i})
                    SET k.source_note_id=$s
                    """,
                    i=main["id"],
                    s=note_id,
                )
            ).consume()

            p["note_id"] = note_id

        for b in drop:
            await (await s.run("MATCH (b:KnowledgeNode {id:$i}) DETACH DELETE b", i=b["id"])).consume()


async def _attach_orphans(driver, uid: str, plan: list[dict]) -> dict[str, int]:
    """把没有父节点的知识点挂回书本。

    快照里有 367 个知识点没有任何 `CHILD_OF` 边，其中 161 个连来源笔记都没有、学科也是
    「其他」——它们计入 `study-profile` 的 702，却不出现在书架上，导致「共 702 个知识点」
    与「书架加起来 285 个」对不上。这里按学科归位，实在无学科的统一收进一本综合笔记。
    """
    async with driver.session() as s:
        # 学科 -> 书名 -> 书 id
        title_to_id: dict[str, str] = {}
        res = await s.run(
            "MATCH (b:KnowledgeNode {node_type:'book', user_id:$u}) RETURN b.id AS id, b.name AS name",
            u=uid,
        )
        async for r in res:
            title_to_id[r["name"]] = r["id"]

        async def _ensure_book(title: str) -> str | None:
            if title in title_to_id:
                return title_to_id[title]
            if title != FALLBACK_TITLE:
                return None
            res = await s.run(
                """
                CREATE (b:KnowledgeNode {
                    id: randomUUID(), node_type:'book', type:'book', user_id:$u,
                    name:$n, subject:'跨学科', summary:'', mastery:0.0
                })
                RETURN b.id AS id
                """,
                u=uid,
                n=title,
            )
            bid = (await res.single())["id"]
            title_to_id[title] = bid
            return bid

        async def _sweep(only_knowledge: bool) -> dict[str, int]:
            """把「沿 parent_id 走不到任何书」的节点按学科挂回书本。

            书架与树接口都按 `parent_id` 属性重建层级（见 services/graph/tree.py），
            所以判定必须用 parent_id 而不是 CHILD_OF 关系——合并旧书时会把子节点的
            parent_id 留成已删除的 id，这些节点会从树里消失。
            """
            res = await s.run(
                """
                MATCH (x:KnowledgeNode {user_id:$u})
                WHERE x.node_type IN ['category','knowledge']
                RETURN x.id AS id, x.parent_id AS parent_id, x.node_type AS kind, x.subject AS subject
                """,
                u=uid,
            )
            nodes = [r.data() async for r in res]

            by_parent: dict[str, list[str]] = {}
            info = {n["id"]: n for n in nodes}
            for n in nodes:
                if n["parent_id"]:
                    by_parent.setdefault(n["parent_id"], []).append(n["id"])

            reachable: set[str] = set()
            stack = list(title_to_id.values())
            while stack:
                cur = stack.pop()
                for child in by_parent.get(cur, []):
                    if child not in reachable:
                        reachable.add(child)
                        stack.append(child)

            want_kind = "knowledge" if only_knowledge else "category"
            buckets: dict[str, list[str]] = {}
            for n in nodes:
                if n["id"] in reachable or n["kind"] != want_kind:
                    continue
                sub = (n["subject"] or "").strip()
                title = None if sub in UNCLASSIFIED_SUBJECTS else TITLE_BY_SUBJECT.get(sub)
                buckets.setdefault(title or FALLBACK_TITLE, []).append(n["id"])

            done: dict[str, int] = {}
            for title, ids in buckets.items():
                book_id = await _ensure_book(title)
                if not book_id:
                    continue
                await (
                    await s.run(
                        """
                        UNWIND $ids AS kid
                        MATCH (k:KnowledgeNode {id:kid})
                        MATCH (b:KnowledgeNode {id:$bid})
                        MERGE (k)-[:CHILD_OF]->(b)
                        SET k.parent_id = $bid, k.source_note_id = $nid
                        """,
                        ids=ids,
                        bid=book_id,
                        nid=note_id_for(title),
                    )
                ).consume()
                done[title] = done.get(title, 0) + len(ids)
            return done

        # 目录先归位，知识点再扫一遍：否则挂在断链目录下的知识点会被重复直挂到书上
        attached = await _sweep(False)
        for title, n in (await _sweep(True)).items():
            attached[title] = attached.get(title, 0) + n

        # 最后把 CHILD_OF 关系与 parent_id 属性对齐：`_relink_parent` 的做法是
        # 「先删光再从 parent_id 重建」，否则重复挂载会留下多条父边，同一知识点
        # 被两本书各算一次
        await (await s.run(
            "MATCH (:KnowledgeNode {user_id:$u})-[r:CHILD_OF]->(:KnowledgeNode) DELETE r",
            u=uid,
        )).consume()
        await (await s.run(
            """
            MATCH (n:KnowledgeNode {user_id:$u})
            WHERE n.parent_id IS NOT NULL
            MATCH (p:KnowledgeNode {id:n.parent_id, user_id:$u})
            MERGE (n)-[:CHILD_OF]->(p)
            """,
            u=uid,
        )).consume()
        return attached


async def _orphan_summary(driver, uid: str) -> dict[str, int]:
    async with driver.session() as s:
        res = await s.run(
            """
            MATCH (k:KnowledgeNode {node_type:'knowledge', user_id:$u})
            OPTIONAL MATCH (p:KnowledgeNode {id:k.parent_id})
            WITH k, p, coalesce(trim(k.subject),'') AS sub
            WHERE k.parent_id IS NULL OR p IS NULL
            RETURN count(k) AS total,
                   sum(CASE WHEN sub IN $blank THEN 1 ELSE 0 END) AS unclassified
            """,
            u=uid,
            blank=list(UNCLASSIFIED_SUBJECTS),
        )
        row = await res.single()
        return {"total": row["total"] or 0, "unclassified": row["unclassified"] or 0}


async def _collect_notes(driver, uid: str) -> list[dict]:
    """按最终结构统计每本书的知识点/关系数，供关系库写笔记用。"""
    async with driver.session() as s:
        res = await s.run(
            "MATCH (b:KnowledgeNode {node_type:'book', user_id:$u}) RETURN b.id AS id, b.name AS name",
            u=uid,
        )
        books = [r.data() async for r in res]

    notes = []
    for b in books:
        nodes, edges = await _counts(driver, b["id"])
        notes.append(
            {
                "id": note_id_for(b["name"]),
                "book_id": b["id"],
                "title": b["name"],
                "nodes": nodes,
                "edges": edges,
                "old_name": b["name"],
            }
        )
    return notes


def _write_notes(uid: str, notes: list[dict]) -> None:
    db = _sqlite_path()
    con = sqlite3.connect(db)
    now = datetime.now()
    try:
        for idx, n in enumerate(notes):
            uploaded = (now - timedelta(days=3 + idx * 2)).strftime("%Y-%m-%d %H:%M:%S.%f")
            processed = (now - timedelta(days=3 + idx * 2, minutes=-2)).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
            content = (
                f"{n['title']}\n\n"
                f"本笔记由「{n['old_name']}」整理而来，"
                f"已抽取 {n['nodes']} 个知识点、{n['edges']} 条关联关系。"
            )
            con.execute(
                """
                INSERT INTO notes (id, user_id, title, content, format, tags,
                                   file_path, task_id, upload_time, status,
                                   nodes_count, edges_count, error_message, processed_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, content=excluded.content,
                    status=excluded.status, nodes_count=excluded.nodes_count,
                    edges_count=excluded.edges_count, processed_time=excluded.processed_time
                """,
                (
                    n["id"],
                    uid,
                    n["title"],
                    content,
                    "md",
                    "演示",
                    None,
                    None,
                    uploaded,
                    "success",
                    n["nodes"],
                    n["edges"],
                    None,
                    processed,
                ),
            )
        con.commit()
    finally:
        con.close()


async def main() -> None:
    ap = argparse.ArgumentParser(description="重整演示账号书架")
    ap.add_argument("--phone", default=DEFAULT_PHONE)
    ap.add_argument("--write", action="store_true", help="真正写库（默认只预览）")
    args = ap.parse_args()

    from neo4j import AsyncGraphDatabase

    uid = _resolve_user(args.phone)
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    try:
        books = await _collect(driver, uid)
        plan, drop, keep = _plan(books)
        print(f"[i] 目标用户 : {args.phone} -> {uid}")
        print(f"[i] 现有书本 : {len(books)} 本")
        print()

        total_others = sum(len(p["others"]) for p in plan)
        for p in plan:
            old = f"{p['main']['name']} (+{len(p['others'])} 本合并)" if p["others"] else p["main"]["name"]
            print(f"  {old:<46} -> {p['title']}")
        for b in keep:
            print(f"  {b['name']:<46} -> (保持原样，未映射学科)")
        for b in drop:
            print(f"  {b['name']:<46} -> (删除：空书且无学科)")

        print()
        print(f"[i] 合并后书本数 : {len(plan) + len(keep)} 本（合并掉 {total_others} 本，删除 {len(drop)} 本）")

        orphans = await _orphan_summary(driver, uid)
        print(f"[i] 无父节点知识点 : {orphans['total']} 个（其中无学科 {orphans['unclassified']} 个将收进「{FALLBACK_TITLE}」）")

        if not args.write:
            print("[dry-run] 未写库。加 --write 执行。")
            return

        await _apply(driver, uid, plan, drop)
        attached = await _attach_orphans(driver, uid, plan)
        total_attached = sum(attached.values())
        print(f"[i] 已归位无父节点知识点 : {total_attached} 个")

        notes = await _collect_notes(driver, uid)
        _write_notes(uid, notes)
        print()
        print(f"[✓] 图谱已重整，关系库补入 {len(notes)} 条笔记录")
        for n in notes:
            print(f"      {n['title']:<30} {n['nodes']:>3} 知识点 / {n['edges']:>3} 关系")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
