"""内置只读图谱服务（演示兜底）。

用途：当环境没有可用的 Neo4j（例如免费云部署、评委本地只跑 SQLite）时，
用随仓库分发的演示图谱（`backend/demo/neo4j-demo.jsonl`）提供**只读**图谱能力，
让「知识图谱 / 知识画像」等核心页面依然有内容，而不是空白或报错。

设计边界（很重要）：
  - **仅对演示账号生效**：其他用户一律返回空结果，绝不把演示数据当成用户自己的数据
  - **只读**：写操作（新增/修改/删除节点、写入抽取结果等）统一抛出清晰错误
  - 数据只加载一次并缓存；文件缺失或损坏时退化为"空图谱"，不影响服务启动

组合方式见 `app/services/graph/__init__.py` 与 `app/api/deps/graph_deps.py`。
"""

from __future__ import annotations

import json
import os
from collections import Counter

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

logger = get_logger(__name__)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEMO_GRAPH = os.path.join(BACKEND_DIR, "demo", "neo4j-demo.jsonl")

_READ_ONLY_HINT = (
    "当前为演示模式（内置只读图谱），不支持修改知识图谱。"
    "如需完整功能，请配置 NEO4J_URI 连接 Neo4j 后重试。"
)


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

    def __init__(self) -> None:
        self._data = _GraphData.instance()

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
        nodes = self._data.visible_nodes(user_id)
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
        nodes = {n["id"]: n for n in self._data.visible_nodes(user_id)}
        out = [dict(nodes[cid]) for cid in self._data.children.get(parent_id, []) if cid in nodes]
        return out

    # ---------- 读：节点 / 整图 ----------
    async def get_all_nodes(self, user_id: str) -> list[dict]:
        return [dict(n) for n in self._data.visible_nodes(user_id)]

    async def get_node_detail(self, user_id: str, node_id: str) -> dict | None:
        node = self._data.nodes.get(node_id)
        if not node or node.get("user_id") != user_id:
            return None
        return dict(node)

    async def get_user_graph(
        self,
        user_id: str,
        subject: str | None = None,
        note_id: str | None = None,
    ) -> dict:
        nodes = self._data.visible_nodes(user_id)
        if subject:
            nodes = [n for n in nodes if n.get("subject") == subject]
        if note_id:
            nodes = [n for n in nodes if n.get("source_note_id") == note_id]
        ids = {n["id"] for n in nodes}
        return {
            "nodes": [dict(n) for n in nodes],
            "edges": self._edges_within(ids),
        }

    # ---------- 读：统计 ----------
    async def get_subject_distribution(self, user_id: str) -> dict[str, int]:
        distribution: dict[str, int] = {}
        for node in self._data.visible_nodes(user_id):
            key = node.get("subject") or UNCLASSIFIED_SUBJECT
            distribution[key] = distribution.get(key, 0) + 1
        return distribution

    async def get_mastery_overview(self, user_id: str) -> dict:
        knowledge = [
            n
            for n in self._data.visible_nodes(user_id)
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
        for node in self._data.visible_nodes(user_id):
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
        return sum(
            1 for n in self._data.visible_nodes(user_id) if n.get("origin") == origin
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
        for node in self._data.visible_nodes(user_id):
            text = f"{node.get('name') or ''}{node.get('summary') or ''}"
            score = VectorMixin.keyword_score(q, text)
            if score > 0:
                scored.append((score, dict(node)))
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
