"""把广场上的种子演示帖挂到演示账号名下，修好「演示叙事断链」。

背景：广场里 9 篇演示帖的作者是种子账号（16723456175 / 16700006175 / 13910000001），
而演示号 `13900000001` 名下几乎没有帖子。后果是：

- 「我的发布」在演示号上是空的，演示时无法讲「我发布的图谱」；
- 评委用演示号去点赞/评论这些帖子时，通知只会落到种子账号，**演示号永远收不到**，
  与「互动实时通知作者」的叙事对不上。

帖子内容是自包含的（`graph_snapshot` 存的是快照 JSON），只改 `user_id` 不影响
克隆/详情/点赞，也不会破坏原作者的书架与图谱。

用法
----
    python backend/scripts/attach_demo_posts.py            # 只预览
    python backend/scripts/attach_demo_posts.py --write    # 执行（幂等）
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

DEFAULT_DB = os.path.join(BACKEND_DIR, "krp.db")
DEFAULT_DEMO_PHONE = "13900000001"


def demo_user_id(con: sqlite3.Connection, phone: str) -> str | None:
    row = con.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
    return row[0] if row else None


def main() -> int:
    parser = argparse.ArgumentParser(description="把种子演示帖挂到演示账号名下")
    parser.add_argument("--write", action="store_true", help="真正写入（默认只预览）")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 路径")
    parser.add_argument("--demo-phone", default=DEFAULT_DEMO_PHONE, help="演示账号手机号")
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    uid = demo_user_id(con, args.demo_phone)
    if not uid:
        print(f"[ERR] 找不到演示账号 {args.demo_phone}")
        return 1

    rows = con.execute(
        """
        SELECT p.id, p.title, p.user_id, u.phone AS author_phone
        FROM community_posts p
        LEFT JOIN users u ON u.id = p.user_id
        WHERE p.user_id != ?
        ORDER BY p.created_at ASC
        """,
        (uid,),
    ).fetchall()

    if not rows:
        print("[OK] 所有帖子都已挂在演示号名下，无需处理")
        con.close()
        return 0

    print(f"演示账号 {args.demo_phone} → user_id={uid}")
    print(f"待迁移帖子 {len(rows)} 篇：")
    for r in rows:
        print(f"  - {r['title'][:36]}（作者 {r['author_phone'] or '未知'}）")

    if not args.write:
        print("\n[DRY-RUN] 未写入。加 --write 执行。")
        con.close()
        return 0

    con.executemany(
        "UPDATE community_posts SET user_id = ? WHERE id = ?",
        [(uid, r["id"]) for r in rows],
    )
    con.commit()
    total = con.execute(
        "SELECT count(*) FROM community_posts WHERE user_id = ?", (uid,)
    ).fetchone()[0]
    print(f"\n[OK] 已迁移 {len(rows)} 篇；演示号名下现有 {total} 篇帖子")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
