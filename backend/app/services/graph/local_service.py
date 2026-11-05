"""内置只读图谱服务（演示兜底）。

用途：当环境没有可用的 Neo4j（例如免费云部署、评委本地只跑 SQLite）时，
用随仓库分发的演示图谱（`backend/demo/neo4j-demo.jsonl`）提供**只读**图谱能力，
让「知识图谱 / 知识画像」等核心页面依然有内容，而不是空白或报错。

设计边界（很重要）：
  - **仅对演示账号生效**：其他用户一律返回空结果，绝不把演示数据当成用户自己的数据
  - **图谱文件只读**：新增/修改/删除节点、写入抽取结果等一律拒绝
  - **掌握度可回写**：答题产生的掌握度不写回 jsonl，而是落在本地库的
    `node_mastery_overrides` 覆盖层里，读的时候合并。否则「答题 → 掌握度变化 →
    第二天换一批题」这条闭环在演示环境里是断的，用户会看到同一批题反复出现。
  - 数据只加载一次并缓存；文件缺失或损坏时退化为"空图谱"，不影响服务启动

组合方式见 `app/services/graph/__init__.py` 与 `app/api/deps/graph_deps.py`。
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone

from app.core.exceptions import ForbiddenException
from app.core.logger import get_logger
from app.services.graph.constants import (
    NODE_TYPE_BOOK,
    NODE_TYPE_CATEGORY,
    NODE_TYPE_KNOWLEDGE,
    NOISE_SUBJECTS,
    RELATED_TO,
    UNCLASSIFIED_SUBJECT,
)
from app.services.graph.stats import build_study_profile

logger = get_logger(__name__)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEMO_GRAPH = os.path.join(BACKEND_DIR, "demo", "neo4j-demo.jsonl")

def _days_since_any(value) -> float | None:
    """把演示图谱里的 last_reviewed 折算成天数。

    同一份 jsonl 里这个字段可能是 ISO 字符串、毫秒时间戳或 neo4j DateTime，
    统一在这里兜住，避免筛选逻辑散落各处的类型判断。
    """
    if value is None or value == "":
        return None

    dt: datetime | None = None
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    elif isinstance(value, datetime):
        dt = value
    else:
        to_native = getattr(value, "to_native", None)
        if not callable(to_native):
            return None
        try:
            dt = to_native()
        except Exception:  # noqa: BLE001 - 时间格式异常不应影响复习筛选
            return None

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)


_READ_ONLY_HINT = (
    "当前为演示模式（内置只读图谱），不支持修改知识图谱。"
    "如需完整功能，请配置 NEO4J_URI 连接 Neo4j 后重试。"
)


def _as_iso(value: datetime | None) -> str | None:
    """日期统一成带时区的 ISO 串（覆盖层存的 naive 时间按 UTC 解释）。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


#: 复习队列里「多久没看」的封顶值：再久也不会比两个月没看更紧急，
#: 否则一份很旧的图谱会让所有新知识点永远排在最后。
REVIEW_DAYS_CAP = 60.0


def review_sort_key(mastery: float, days: float | None) -> tuple[float, float]:
    """待复习排序键：先按「多久没复习」倒序，再按掌握度升序。

    只按掌握度排会让 0 分的新知识点长期霸占队列（学过的内容再也回不来），
    这也是「每天都是同一批题」的成因之一。
    """
    due = min(days, REVIEW_DAYS_CAP) if days is not None else 0.0
    return (-due, mastery)


class _GraphData:
    """演示图谱的内存索引（进程内单例）。"""

    _instance: "_GraphData | None" = None

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.children: dict[str | None, list[str]] = {}
        self.demo_user_id: str | None = None
        self._load()

    @classmethod
    def instance(cls) -> "_GraphData":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self) -> None:
        if not os.path.isfile(DEMO_GRAPH):
            logger.info("内置图谱：未找到演示图谱文件（%s），图谱能力为空", DEMO_GRAPH)
            return
        try:
            raw_nodes: list[dict] = []
            with open(DEMO_GRAPH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("kind") == "node":
                        props = rec.get("props") or {}
                        if props.get("id"):
                            self.nodes[props["id"]] = props
                            raw_nodes.append(props)
                    elif rec.get("kind") == "edge":
                        self.edges.append(rec)
            users = Counter(n.get("user_id") for n in raw_nodes if n.get("user_id"))
            self.demo_user_id = users.most_common(1)[0][0] if users else None
            for node in self.nodes.values():
                self.children.setdefault(node.get("parent_id"), []).append(node["id"])
            for ids in self.children.values():
                ids.sort(key=lambda nid: (self.nodes[nid].get("sort_order") or 999999, self.nodes[nid].get("name") or ""))
            logger.info(
                "内置图谱已加载：%d 个节点 / %d 条关系（演示账号 %s）",
                len(self.nodes),
                len(self.edges),
                self.demo_user_id,
            )
        except Exception:
            logger.warning("内置图谱加载失败（将退化为空图谱）", exc_info=True)

    # ---------- 查询辅助 ----------
    def visible_nodes(self, user_id: str) -> list[dict]:
        if not user_id or user_id != self.demo_user_id:
            return []
        return list(self.nodes.values())

    def subtree_ids(self, book_id: str) -> set[str]:
        ids: set[str] = set()
        stack = [book_id]
        while stack:
            current = stack.pop()
            for child_id in self.children.get(current, []):
                if child_id not in ids:
                    ids.add(child_id)
                    stack.append(child_id)
        return ids


class LocalGraphService:
    """与 `GraphService` 接口兼容的只读实现（演示用）。"""

    #: 演示图谱不带向量，检索走关键词（二元组）而非 embedding
    supports_vector = False

    def __init__(self, session_factory=None) -> None:
        self._data = _GraphData.instance()
        # 覆盖层持久化用的会话工厂；测试或未接库时传 None，退化为进程内覆盖
        self._session_factory = session_factory
        self._overrides: dict[str, dict] | None = None

    # ---------- 掌握度覆盖层 ----------
    async def _load_overrides(self) -> dict[str, dict]:
        """懒加载本地掌握度覆盖层：只在第一次读时查一次库。"""
        if self._overrides is not None:
            return self._overrides

        overrides: dict[str, dict] = {}
        if self._session_factory is not None:
            try:
                from sqlalchemy import select

                from app.models.reflection import NodeMasteryOverride

                async with self._session_factory() as session:
                    rows = (
                        (await session.execute(select(NodeMasteryOverride))).scalars().all()
                    )
                for row in rows:
                    overrides[row.node_id] = {
                        "mastery": float(row.mastery or 0.0),
                        "last_reviewed": _as_iso(row.last_reviewed),
                    }
            except Exception:  # noqa: BLE001 - 覆盖层读不出来不应影响演示图谱
                logger.warning("读取掌握度覆盖层失败，按演示图谱原值继续", exc_info=True)
        self._overrides = overrides
        return overrides

    def _merge(self, node: dict) -> dict:
        merged = dict(node)
        override = (self._overrides or {}).get(node.get("id"))
        if override:
            merged.update(override)
        return merged

    async def _nodes(self, user_id: str) -> list[dict]:
        await self._load_overrides()
        return [self._merge(n) for n in self._data.visible_nodes(user_id)]

    async def _node(self, user_id: str, node_id: str) -> dict | None:
        node = self._data.nodes.get(node_id)
        if not node or node.get("user_id") != user_id:
            return None
        await self._load_overrides()
        return self._merge(node)

    async def update_mastery(
        self, user_id: str, node_id: str, mastery: float
    ) -> dict | None:
        """把答题得到的掌握度写进覆盖层（jsonl 只读，用户数据落本地库）。

        这是演示环境里唯一被允许的「写」：它写的是用户自己的学习结果，
        不是演示图谱本身。写进去之后，出题筛选与知识画像立刻能看到变化。
        """
        node = await self._node(user_id, node_id)
        if node is None:
            return None

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        override = {"mastery": float(mastery), "last_reviewed": _as_iso(now)}
        await self._load_overrides()
        assert self._overrides is not None
        self._overrides[node_id] = override
        await self._persist_override(user_id, node_id, float(mastery), now)
        merged = dict(node)
        merged.update(override)
        return merged

    async def _persist_override(
        self, user_id: str, node_id: str, mastery: float, now: datetime
    ) -> None:
        if self._session_factory is None:
            return
        try:
            from sqlalchemy import select

            from app.models.reflection import NodeMasteryOverride

            async with self._session_factory() as session:
                row = (
                    await session.execute(
                        select(NodeMasteryOverride).where(
                            NodeMasteryOverride.user_id == user_id,
                            NodeMasteryOverride.node_id == node_id,
                        )
                    )
                ).scalars().first()
                if row is None:
                    session.add(
                        NodeMasteryOverride(
                            user_id=user_id,
                            node_id=node_id,
                            mastery=mastery,
                            last_reviewed=now,
                        )
                    )
                else:
                    row.mastery = mastery
                    row.last_reviewed = now
                await session.commit()
        except Exception:  # noqa: BLE001 - 落库失败时至少进程内覆盖仍然有效
            logger.warning(
                "掌握度覆盖层写库失败（本次运行内仍生效）: user=%s node=%s",
                user_id,
                node_id,
                exc_info=True,
            )

    # ---------- 读：书架 / 知识树 ----------
    async def get_books(self, user_id: str) -> list[dict]:
        books = [
            dict(n)
            for n in self._data.visible_nodes(user_id)
            if n.get("node_type") == NODE_TYPE_BOOK
        ]
        for book in books:
            book["node_count"] = len(self._data.subtree_ids(book["id"]))
        books.sort(key=lambda b: b.get("name") or "")
        return books

    async def get_tree(self, user_id: str, book_id: str) -> dict | None:
        nodes = await self._nodes(user_id)
        book = next(
            (
                n
                for n in nodes
                if n.get("id") == book_id and n.get("node_type") == NODE_TYPE_BOOK
            ),
            None,
        )
        if book is None:
            return None
        keep = self._data.subtree_ids(book_id) | {book_id}
        tree_nodes = [
            dict(n)
            for n in nodes
            if n.get("id") in keep
            and n.get("node_type") in (NODE_TYPE_CATEGORY, NODE_TYPE_KNOWLEDGE)
        ]
        tree_nodes.sort(key=lambda n: (n.get("sort_order") or 999999, n.get("name") or ""))
        edges = self._edges_within(keep)
        return {"book": dict(book), "nodes": tree_nodes, "edges": edges}

    async def get_children(self, user_id: str, parent_id: str) -> list[dict]:
        nodes = {n["id"]: n for n in await self._nodes(user_id)}
        out = [dict(nodes[cid]) for cid in self._data.children.get(parent_id, []) if cid in nodes]
        return out

    # ---------- 读：节点 / 整图 ----------
    async def get_all_nodes(self, user_id: str) -> list[dict]:
        return await self._nodes(user_id)

    async def get_node_detail(self, user_id: str, node_id: str) -> dict | None:
        return await self._node(user_id, node_id)

    async def get_nodes_for_review(
        self,
        user_id: str,
        mastery_threshold: float = 60.0,
        days_threshold: int = 7,
        limit: int = 5,
    ) -> list[dict]:
        """只读版待复习节点：与 Neo4j 侧同一套筛选口径（掌握度低 / 没复习过 / 久未复习）。

        没有这个实现，纯演示环境（无 Neo4j）打开「每日反思」会直接 403，
        而反思是作品的核心闭环——演示环境最不该缺的就是它。

        排序按「间隔重复」而不是「掌握度升序」：先排最久没回顾的，再排最弱的。
        只按掌握度排会让 0 分的新知识点永远霸占队列，学过的内容再也回不来。
        """
        await self._load_overrides()
        candidates: list[tuple[float, float, dict]] = []
        for node in self._data.visible_nodes(user_id):
            if node.get("node_type") != NODE_TYPE_KNOWLEDGE:
                continue
            node = self._merge(node)
            mastery = node.get("mastery")
            mastery = float(mastery) if isinstance(mastery, (int, float)) else 0.0
            days = _days_since_any(node.get("last_reviewed"))
            if mastery < mastery_threshold or days is None or days >= days_threshold:
                candidates.append((mastery, days, dict(node)))
        candidates.sort(key=lambda item: review_sort_key(item[0], item[1]))
        return [node for _, _, node in candidates[:limit]]

    async def get_user_graph(
        self,
        user_id: str,
        subject: str | None = None,
        note_id: str | None = None,
    ) -> dict:
        nodes = await self._nodes(user_id)
        if subject:
            nodes = [n for n in nodes if n.get("subject") == subject]
        if note_id:
            nodes = [n for n in nodes if n.get("source_note_id") == note_id]
        ids = {n["id"] for n in nodes}
        return {
            "nodes": nodes,
            "edges": self._edges_within(ids),
        }

    # ---------- 读：统计 ----------
    async def get_subject_distribution(self, user_id: str) -> dict[str, int]:
        distribution: dict[str, int] = {}
        for node in await self._nodes(user_id):
            key = node.get("subject") or UNCLASSIFIED_SUBJECT
            distribution[key] = distribution.get(key, 0) + 1
        return distribution

    async def get_mastery_overview(self, user_id: str) -> dict:
        knowledge = [
            n
            for n in await self._nodes(user_id)
            if n.get("node_type") == NODE_TYPE_KNOWLEDGE
        ]
        if not knowledge:
            return {"total": 0, "avg_mastery": 0.0, "weak": 0, "basic": 0, "proficient": 0}
        values = [float(n.get("mastery") or 0.0) for n in knowledge]
        return {
            "total": len(values),
            "avg_mastery": sum(values) / len(values),
            "weak": sum(1 for v in values if v < 60),
            "basic": sum(1 for v in values if 60 <= v < 80),
            "proficient": sum(1 for v in values if v >= 80),
        }

    async def get_subject_stats(self, user_id: str) -> list[dict]:
        buckets: dict[str, list[float]] = {}
        for node in await self._nodes(user_id):
            if node.get("node_type") != NODE_TYPE_KNOWLEDGE:
                continue
            subject = node.get("subject") or UNCLASSIFIED_SUBJECT
            if subject in NOISE_SUBJECTS:
                continue
            buckets.setdefault(subject, []).append(float(node.get("mastery") or 0.0))
        stats = [
            {
                "subject": subject,
                "node_count": len(values),
                "avg_mastery": (sum(values) / len(values)) if values else 0.0,
            }
            for subject, values in buckets.items()
        ]
        stats.sort(key=lambda s: (-s["node_count"], s["subject"]))
        return stats

    async def count_nodes_by_origin(self, user_id: str, origin: str) -> int:
        return sum(1 for n in await self._nodes(user_id) if n.get("origin") == origin)

    async def get_study_profile(self, user_id: str) -> dict:
        """六维学习画像（只读版）。

        这个方法必须实现：`__getattr__` 的兜底会把任何未实现的读方法变成
        「不支持修改知识图谱」的 403——一个只读接口报这种错，比直接没有数据还难解释。
        算法与 Neo4j 版共用 `build_study_profile`，保证两套后端分数一致。
        """
        knowledge = [
            n
            for n in await self._nodes(user_id)
            if n.get("node_type") == NODE_TYPE_KNOWLEDGE
        ]
        if not knowledge:
            return {"total": 0, "dimensions": []}

        values = [float(n.get("mastery") or 0.0) for n in knowledge]
        total = len(values)
        reviewed = sum(
            1
            for n in knowledge
            if float(n.get("mastery") or 0.0) > 0 or n.get("last_reviewed")
        )
        subjects = {
            n.get("subject")
            for n in knowledge
            if n.get("subject") and n.get("subject") not in NOISE_SUBJECTS
        }
        return build_study_profile(
            total=total,
            avg_mastery=sum(values) / total,
            proficient=sum(1 for v in values if v >= 80),
            solid=sum(1 for v in values if v >= 60),
            reviewed=reviewed,
            subject_count=len(subjects),
        )

    # ---------- 读：检索（数字分身问答的降级路径） ----------
    async def vector_search(self, user_id: str, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        """无向量索引时退化为关键词（字符二元组）检索。"""
        return await self.keyword_search(user_id, query, top_k=top_k)

    async def keyword_search(self, user_id: str, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        from app.services.graph.vector import VectorMixin

        q = (query or "").strip()
        if not q:
            return []
        scored: list[tuple[float, dict]] = []
        for node in await self._nodes(user_id):
            text = f"{node.get('name') or ''}{node.get('summary') or ''}"
            score = VectorMixin.keyword_score(q, text)
            if score > 0:
                scored.append((score, node))
        scored.sort(key=lambda item: -item[0])
        return [{**node, "score": round(score, 4)} for score, node in scored[:top_k]]

    # ---------- 辅助 ----------
    def _edges_within(self, node_ids: set[str]) -> list[dict]:
        out: list[dict] = []
        for edge in self._data.edges:
            if edge.get("type") != RELATED_TO:
                continue
            src, dst = edge.get("src"), edge.get("dst")
            if src in node_ids and dst in node_ids:
                props = edge.get("props") or {}
                out.append(
                    {
                        "id": props.get("id") or f"{src}->{dst}",
                        "source_id": src,
                        "target_id": dst,
                        "relation": props.get("relation"),
                        "weight": props.get("weight", 1.0),
                    }
                )
        return out

    # ---------- 写操作一律拒绝 ----------
    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        async def _unsupported(*_args, **_kwargs):
            raise ForbiddenException(_READ_ONLY_HINT)

        return _unsupported
