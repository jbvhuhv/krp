"""清理演示库里的测试残留，让「笔记 / 社区 / 书架」三个页面都经得起放大看。

清理范围刻意收窄——只动三类明确属于测试产物的数据：

1. **并发测试帖**：压测脚本留下的「并发测试帖 第N 轮」，社区首页一眼可见；
2. **空用户**：没有任何笔记 / 帖子 / 评论 / 点赞的账号，纯粹是登录测试建出来的；
3. **原始文件已丢失的失败笔记**：`re-extract` 端点要求原文件存在，这类笔记点「重抽」
   必然 400「原始文件已丢失」，对用户是死路。

**不动**的东西（说明理由，免得下次误删）：
- 有社区内容的测试账号：评论和点赞分散在 7 个账号上，删掉会让评论区变成「已注销用户」；
- `演示-抽取失败示例.txt`：是故意造的失败态样本，用于演示抽取失败的表现；
- 演示账号（默认 `13900000001`）名下的任何笔记。

用法
----
    python backend/scripts/clean_demo_data.py            # 只预览
    python backend/scripts/clean_demo_data.py --write    # 执行
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings  # noqa: E402

DEFAULT_PHONE = "13900000001"
JUNK_POST = re.compile(r"(并发测试帖|测试帖\s*第)")


def _sqlite_path() -> str:
    url = settings.POSTGRES_URL or ""
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        raise SystemExit(f"[ERROR] 当前关系库不是 SQLite（{url}），本脚本仅用于本地开发环境。")
    raw = url[len(prefix) :]
    if raw.startswith("./"):
        return os.path.join(BACKEND_DIR, raw[2:])
    return raw if os.path.isabs(raw) else os.path.join(BACKEND_DIR, raw)


def _resolve_upload(path: str) -> str:
    """`file_path` 存的是 `./uploads\\xxx.jpg` 这类相对路径，按 backend 目录解析。"""
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(BACKEND_DIR, path))


def main() -> None:
    ap = argparse.ArgumentParser(description="清理演示库的测试残留")
    ap.add_argument("--phone", default=DEFAULT_PHONE, help="演示账号手机号（其笔记永不删除）")
    ap.add_argument("--write", action="store_true", help="真正写库（默认只预览）")
    args = ap.parse_args()

    db = _sqlite_path()
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        demo = con.execute("SELECT id FROM users WHERE phone=?", (args.phone,)).fetchone()
        if not demo:
            raise SystemExit(f"[ERROR] 找不到手机号 {args.phone} 的用户")
        demo_id = demo["id"]

        posts = [
            r["id"]
            for r in con.execute("SELECT id, title FROM community_posts")
            if JUNK_POST.search(r["title"] or "")
        ]

        users = [
            r["id"]
            for r in con.execute(
                """
                SELECT u.id FROM users u
                WHERE u.id != ?
                  AND NOT EXISTS (SELECT 1 FROM notes WHERE user_id=u.id)
                  AND NOT EXISTS (SELECT 1 FROM community_posts WHERE user_id=u.id)
                  AND NOT EXISTS (SELECT 1 FROM community_comments WHERE user_id=u.id)
                  AND NOT EXISTS (SELECT 1 FROM community_likes WHERE user_id=u.id)
                """,
                (demo_id,),
            )
        ]

        lost_notes = []
        for r in con.execute(
            "SELECT id, title, file_path FROM notes WHERE status='failed' AND user_id != ?",
            (demo_id,),
        ):
            # `演示-*` 是刻意造的失败态样本，保留用于演示抽取失败的表现
            if (r["title"] or "").startswith("演示-"):
                continue
            if not os.path.exists(_resolve_upload(r["file_path"])):
                lost_notes.append((r["id"], r["title"]))

        print(f"[i] 关系库 : {db}")
        print(f"[i] 演示号 : {args.phone} -> {demo_id}")
        print()
        print(f"  测试帖      : {len(posts)} 条")
        for pid in posts:
            t = con.execute("SELECT title FROM community_posts WHERE id=?", (pid,)).fetchone()
            print(f"      - {t['title']}")
        print(f"  空用户      : {len(users)} 个")
        print(f"  原文件已丢的失败笔记 : {len(lost_notes)} 条")
        for _, title in lost_notes:
            print(f"      - {title[:44]}")

        if not args.write:
            print("\n[dry-run] 未写库。加 --write 执行。")
            return

        with con:
            for pid in posts:
                con.execute("DELETE FROM community_posts WHERE id=?", (pid,))
            for uid in users:
                # 逐表清理，避免留下指向已删用户的孤儿行
                for table in (
                    "community_comments",
                    "community_likes",
                    "notifications",
                    "reflection_records",
                    "reflection_schedules",
                    "chat_messages",
                    "pet_messages",
                    "pets",
                    "avatars",
                    "community_post_views",
                ):
                    cols = {x[1] for x in con.execute(f"PRAGMA table_info({table})")}
                    if "user_id" in cols:
                        con.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
                con.execute("DELETE FROM users WHERE id=?", (uid,))
            for nid, _ in lost_notes:
                con.execute("DELETE FROM notes WHERE id=?", (nid,))

        print()
        print(f"[✓] 已删除 {len(posts)} 条测试帖、{len(users)} 个空用户、{len(lost_notes)} 条死链笔记")
        print(
            "    剩余：用户 "
            f"{con.execute('SELECT count(*) FROM users').fetchone()[0]} / "
            f"笔记 {con.execute('SELECT count(*) FROM notes').fetchone()[0]} / "
            f"帖子 {con.execute('SELECT count(*) FROM community_posts').fetchone()[0]}"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
