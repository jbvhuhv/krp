import uuid
from collections.abc import Iterator
from itertools import count

from app.services.graph.constants import (
    CHILD_OF,
    DEFAULT_RELATION,
    NODE_LABEL,
    NODE_TYPE_BOOK,
    NODE_TYPE_CATEGORY,
    NODE_TYPE_KNOWLEDGE,
    RELATED_TO,
)


class CrudMixin:
    async def create_node(
        self,
        user_id: str,
        name: str,
        summary: str,
        type: str,
        source_note_id: str | None = None,
        subject: str | None = None,
        node_type: str = NODE_TYPE_KNOWLEDGE,
        parent_id: str | None = None,
        origin: str = "user",
        sort_order: int | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> str:
        node_id = str(uuid.uuid4())
        async with self.driver.session() as session:
            await session.run(
                f"""
                CREATE (n:{NODE_LABEL} {{
                    id: $id,
                    user_id: $user_id,
                    name: $name,
                    summary: $summary,
                    type: $type,
                    subject: $subject,
                    source_note_id: $source_note_id,
                    node_type: $node_type,
                    parent_id: $parent_id,
                    mastery: 0.0,
                    origin: $origin,
                    sort_order: $sort_order,
                    x: $x,
                    y: $y
                }})
                """,
                id=node_id,
                user_id=user_id,
                name=name,
                summary=summary,
                type=type,
                subject=subject,
                source_note_id=source_note_id,
                node_type=node_type,
                parent_id=parent_id,
                origin=origin,
                sort_order=sort_order,
                x=x,
                y=y,
            )
            if parent_id:
                await session.run(
                    f"""
                    MATCH (p:{NODE_LABEL} {{id: $parent_id, user_id: $user_id}}),
                          (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                    MERGE (n)-[:{CHILD_OF}]->(p)
                    """,
                    parent_id=parent_id,
                    user_id=user_id,
                    node_id=node_id,
                )
        return node_id

    async def create_edge(
        self,
        user_id: str,
        source_id: str,
        target_id: str,
        relation: str = DEFAULT_RELATION,
        weight: float = 1.0,
    ) -> str | None:
        edge_id = str(uuid.uuid4())
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (a:{NODE_LABEL} {{id: $source_id, user_id: $user_id}}),
                      (b:{NODE_LABEL} {{id: $target_id, user_id: $user_id}})
                CREATE (a)-[r:{RELATED_TO} {{id: $edge_id, relation: $relation, weight: $weight}}]->(b)
                RETURN r.id AS edge_id
                """,
                edge_id=edge_id,
                user_id=user_id,
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                weight=weight,
            )
            record = await result.single()
        if record is None:
            return None
        return edge_id

    async def link_parent(self, user_id: str, node_id: str, parent_id: str) -> bool:
        """为已存在节点补建 CHILD_OF 关系并同步 parent_id 属性（幂等）。"""
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (p:{NODE_LABEL} {{id: $parent_id, user_id: $user_id}}),
                      (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                MERGE (n)-[:{CHILD_OF}]->(p)
                SET n.parent_id = $parent_id
                RETURN n.id AS id
                """,
                parent_id=parent_id,
                user_id=user_id,
                node_id=node_id,
            )
            record = await result.single()
        return record is not None

    async def get_all_nodes(self, user_id: str) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                RETURN n
                """,
                user_id=user_id,
            )
            nodes = []
            async for record in result:
                nodes.append(dict(record["n"]))
            return nodes

    async def get_user_graph(
        self,
        user_id: str,
        subject: str | None = None,
        note_id: str | None = None,
    ) -> dict:
        async with self.driver.session() as session:
            conditions = ["n.user_id = $user_id"]
            params: dict = {"user_id": user_id}
            if subject:
                conditions.append("n.subject = $subject")
                params["subject"] = subject
            if note_id:
                conditions.append("n.source_note_id = $note_id")
                params["note_id"] = note_id
            where_clause = " AND ".join(conditions)
            node_result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL})
                WHERE {where_clause}
                RETURN n
                """,
                **params,
            )

            nodes = []
            node_ids = set()
            async for record in node_result:
                node = dict(record["n"])
                nodes.append(node)
                node_ids.add(node.get("id"))

            edge_result = await session.run(
                f"""
                MATCH (a:{NODE_LABEL} {{user_id: $user_id}})-[r:{RELATED_TO}]->(b:{NODE_LABEL} {{user_id: $user_id}})
                RETURN a.id AS source_id, b.id AS target_id,
                       r.relation AS relation, r.weight AS weight,
                       elementId(r) AS edge_id
                """,
                user_id=user_id,
            )
            edges = []
            async for record in edge_result:
                source_id = record["source_id"]
                target_id = record["target_id"]
                if source_id in node_ids and target_id in node_ids:
                    edges.append({
                        "id": record["edge_id"],
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation": record["relation"],
                        "weight": record.get("weight", 1.0),
                    })

        return {"nodes": nodes, "edges": edges}

    async def get_node_detail(self, user_id: str, node_id: str) -> dict | None:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                RETURN n
                """,
                node_id=node_id,
                user_id=user_id,
            )
            record = await result.single()
            if record is None:
                return None
            return dict(record["n"])

    async def update_node(self, user_id: str, node_id: str, **fields) -> dict | None:
        allowed = {
            "name",
            "summary",
            "type",
            "subject",
            "node_type",
            "parent_id",
            "origin",
            "x",
            "y",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return await self.get_node_detail(user_id, node_id)
        set_clause = ", ".join(f"n.{k} = ${k}" for k in updates)
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                SET {set_clause}
                RETURN n
                """,
                node_id=node_id,
                user_id=user_id,
                **updates,
            )
            record = await result.single()
            if record is None:
                return None
            if "parent_id" in updates:
                await self._relink_parent(
                    session, user_id, node_id, updates["parent_id"]
                )
            return dict(record["n"])

    async def _relink_parent(
        self, session, user_id: str, node_id: str, parent_id: str
    ) -> None:
        await session.run(
            f"""
            MATCH (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
            OPTIONAL MATCH (n)-[r:{CHILD_OF}]->()
            DELETE r
            """,
            node_id=node_id,
            user_id=user_id,
        )
        await session.run(
            f"""
            MATCH (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}}),
                  (p:{NODE_LABEL} {{id: $parent_id, user_id: $user_id}})
            MERGE (n)-[:{CHILD_OF}]->(p)
            """,
            node_id=node_id,
            user_id=user_id,
            parent_id=parent_id,
        )

    async def is_descendant(
        self, user_id: str, ancestor_id: str, candidate_id: str
    ) -> bool:
        """判断 candidate_id 是否为 ancestor_id 的后代节点。

        沿 parent_id 向上追溯，若途中遇到 ancestor_id 则说明构成环。
        自身（candidate_id == ancestor_id）也视为成环，返回 True。
        """
        if not ancestor_id or not candidate_id:
            return False
        nodes = await self.get_all_nodes(user_id)
        parent_of = {n.get("id"): n.get("parent_id") for n in nodes}
        current: str | None = candidate_id
        visited: set[str] = set()
        while current and current not in visited:
            if current == ancestor_id:
                return True
            visited.add(current)
            current = parent_of.get(current)
        return False

    async def count_nodes_by_origin(self, user_id: str, origin: str) -> int:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id, origin: $origin}})
                RETURN count(n) AS total
                """,
                user_id=user_id,
                origin=origin,
            )
            record = await result.single()
            return record["total"] if record else 0

    async def delete_node(self, user_id: str, node_id: str) -> bool:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                node_id=node_id,
                user_id=user_id,
            )
            record = await result.single()
            return bool(record and record["deleted"])

    async def delete_subtree(self, user_id: str, node_id: str) -> int:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (root:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                CALL (root) {{
                    MATCH (root)<-[:{CHILD_OF}*0..]-(desc:{NODE_LABEL} {{user_id: $user_id}})
                    DETACH DELETE desc
                    RETURN count(desc) AS deleted
                }}
                RETURN deleted
                """,
                node_id=node_id,
                user_id=user_id,
            )
            record = await result.single()
            return record["deleted"] if record else 0

    async def delete_by_note_id(self, user_id: str, note_id: str) -> int:
        """按 source_note_id 批量删除该笔记产生的所有图谱节点（含 book 根、目录、知识点）。"""
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id, source_note_id: $note_id}})
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                user_id=user_id,
                note_id=note_id,
            )
            record = await result.single()
            return record["deleted"] if record else 0

    async def delete_all_nodes(self, user_id: str) -> int:
        """删除该用户的全部图谱节点（注销账号时调用，满足个保法的删除权）。"""
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                user_id=user_id,
            )
            record = await result.single()
            return record["deleted"] if record else 0

    async def update_mastery(
        self, user_id: str, node_id: str, mastery: float
    ) -> dict | None:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                SET n.mastery = $mastery, n.last_reviewed = datetime()
                RETURN n
                """,
                node_id=node_id,
                user_id=user_id,
                mastery=mastery,
            )
            record = await result.single()
            if record is None:
                return None
            return dict(record["n"])

    async def get_nodes_for_review(
        self,
        user_id: str,
        mastery_threshold: float = 60.0,
        days_threshold: int = 7,
        limit: int = 5,
    ) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id, node_type: $node_type}})
                WITH n,
                     CASE WHEN n.last_reviewed IS NULL THEN NULL
                          ELSE duration.between(
                                 CASE WHEN valueType(n.last_reviewed) STARTS WITH 'STRING'
                                      THEN datetime(n.last_reviewed)
                                    ELSE n.last_reviewed END,
                                 datetime()
                               ).days
                     END AS d
                WHERE n.mastery < $mastery_threshold
                   OR n.last_reviewed IS NULL
                   OR d >= $days_threshold
                RETURN n
                ORDER BY coalesce(d, -1) DESC, n.mastery ASC
                LIMIT $limit
                """,
                user_id=user_id,
                node_type=NODE_TYPE_KNOWLEDGE,
                mastery_threshold=mastery_threshold,
                days_threshold=days_threshold,
                limit=limit,
            )
            nodes = []
            async for record in result:
                nodes.append(dict(record["n"]))
            return nodes

    async def update_book_name_by_note(
        self, user_id: str, note_id: str, name: str
    ) -> int:
        """把某篇笔记对应的书根节点改名（笔记改标题时同步）。返回受影响节点数。"""
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id, source_note_id: $note_id}})
                WHERE n.node_type = $book_type
                SET n.name = $name
                RETURN count(n) AS c
                """,
                user_id=user_id,
                note_id=note_id,
                book_type=NODE_TYPE_BOOK,
                name=name,
            )
            record = await result.single()
            return int(record["c"]) if record else 0

    async def write_extraction_result(
        self,
        user_id: str,
        note_id: str,
        result: dict,
        book_title: str = "",
        subject_override: str | None = None,
    ) -> None:
        # 用户在「上传笔记」时手动选的学科优先级最高：模型判断经常把公共课
        # 笼统归成「计算机」之类，本人最清楚这份笔记属于哪门课。
        subject = (subject_override or "").strip() or (
            (result.get("subject") or "").strip() or None
        )
        seq = count()
        book_id = await self.create_node(
            user_id=user_id,
            name=book_title or note_id,
            summary=result.get("book_summary", ""),
            type=NODE_TYPE_BOOK,
            subject=subject,
            source_note_id=note_id,
            node_type=NODE_TYPE_BOOK,
            parent_id=None,
            sort_order=next(seq),
        )

        categories = result.get("categories", [])
        if not categories:
            for node in result.get("nodes", []):
                await self.create_node(
                    user_id=user_id,
                    name=node["name"],
                    summary=node.get("summary", ""),
                    type=node.get("type", "concept"),
                    subject=node.get("subject") or subject,
                    source_note_id=note_id,
                    node_type=NODE_TYPE_KNOWLEDGE,
                    parent_id=book_id,
                    sort_order=next(seq),
                )
            return

        name_to_id: dict[str, str] = {}
        for cat in categories:
            await self._write_category(
                user_id, note_id, cat, book_id, name_to_id, subject, seq
            )

        for edge in result.get("edges", []):
            source_id = name_to_id.get(edge.get("source"))
            target_id = name_to_id.get(edge.get("target"))
            if source_id and target_id:
                await self.create_edge(
                    user_id=user_id,
                    source_id=source_id,
                    target_id=target_id,
                    relation=edge.get("relation", DEFAULT_RELATION),
                )

    async def _write_category(
        self,
        user_id: str,
        note_id: str,
        cat: dict,
        parent_id: str,
        name_to_id: dict[str, str],
        subject: str | None = None,
        seq: Iterator[int] | None = None,
    ) -> None:
        cat_id = await self.create_node(
            user_id=user_id,
            name=cat["name"],
            summary=cat.get("summary", ""),
            type=NODE_TYPE_CATEGORY,
            subject=subject,
            source_note_id=note_id,
            node_type=NODE_TYPE_CATEGORY,
            parent_id=parent_id,
            sort_order=next(seq) if seq is not None else None,
        )
        name_to_id[cat["name"]] = cat_id
        for sub in cat.get("categories", []):
            await self._write_category(
                user_id, note_id, sub, cat_id, name_to_id, subject, seq
            )
        for kp in cat.get("knowledge_points", []):
            kp_id = await self.create_node(
                user_id=user_id,
                name=kp["name"],
                summary=kp.get("summary", ""),
                type=kp.get("type", "concept"),
                subject=kp.get("subject") or subject,
                source_note_id=note_id,
                node_type=NODE_TYPE_KNOWLEDGE,
                parent_id=cat_id,
                sort_order=next(seq) if seq is not None else None,
            )
            name_to_id[kp["name"]] = kp_id
