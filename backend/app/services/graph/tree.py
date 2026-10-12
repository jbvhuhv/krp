from app.services.graph.constants import (
    NODE_LABEL,
    NODE_TYPE_BOOK,
    NODE_TYPE_CATEGORY,
    NODE_TYPE_KNOWLEDGE,
    RELATED_TO,
)


class TreeMixin:
    async def get_children(self, user_id: str, parent_id: str) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                WHERE n.parent_id = $parent_id
                RETURN n
                ORDER BY coalesce(n.sort_order, 999999), n.name
                """,
                user_id=user_id,
                parent_id=parent_id,
            )
            children = []
            async for record in result:
                children.append(dict(record["n"]))
            return children

    async def get_books(self, user_id: str) -> list[dict]:
        async with self.driver.session() as session:
            books_result = await session.run(
                f"""
                MATCH (b:{NODE_LABEL} {{user_id: $user_id, node_type: '{NODE_TYPE_BOOK}'}})
                RETURN b
                ORDER BY b.name
                """,
                user_id=user_id,
            )
            books = []
            async for record in books_result:
                books.append(dict(record["b"]))

            nodes_result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                WHERE n.node_type IN ['{NODE_TYPE_CATEGORY}', '{NODE_TYPE_KNOWLEDGE}']
                RETURN n.id AS id, n.parent_id AS parent_id
                """,
                user_id=user_id,
            )
            by_parent: dict[str | None, list[str]] = {}
            async for record in nodes_result:
                pid = record["parent_id"]
                by_parent.setdefault(pid, []).append(record["id"])

            for book in books:
                count = 0
                stack = [book["id"]]
                while stack:
                    current = stack.pop()
                    for child_id in by_parent.get(current, []):
                        count += 1
                        stack.append(child_id)
                book["node_count"] = count

            return books

    async def get_tree(self, user_id: str, book_id: str) -> dict | None:
        async with self.driver.session() as session:
            book_result = await session.run(
                f"""
                MATCH (b:{NODE_LABEL} {{id: $book_id, user_id: $user_id, node_type: '{NODE_TYPE_BOOK}'}})
                RETURN b
                """,
                book_id=book_id,
                user_id=user_id,
            )
            book_record = await book_result.single()
            if book_record is None:
                return None
            book = dict(book_record["b"])

            all_nodes_result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                WHERE n.node_type IN ['{NODE_TYPE_CATEGORY}', '{NODE_TYPE_KNOWLEDGE}']
                RETURN n
                ORDER BY coalesce(n.sort_order, 999999), n.name
                """,
                user_id=user_id,
            )
            all_nodes = []
            async for record in all_nodes_result:
                all_nodes.append(dict(record["n"]))

            descendant_ids: set[str] = set()
            by_parent: dict[str, list[str]] = {}
            id_to_node: dict[str, dict] = {}
            for n in all_nodes:
                nid = n.get("id")
                pid = n.get("parent_id")
                id_to_node[nid] = n
                if pid:
                    by_parent.setdefault(pid, []).append(nid)

            stack = [book_id]
            while stack:
                current = stack.pop()
                for child_id in by_parent.get(current, []):
                    if child_id not in descendant_ids:
                        descendant_ids.add(child_id)
                        stack.append(child_id)

            tree_nodes = [n for n in all_nodes if n.get("id") in descendant_ids]
            tree_node_ids = descendant_ids | {book_id}

            edges_result = await session.run(
                f"""
                MATCH (a:{NODE_LABEL} {{user_id: $user_id}})-[r:{RELATED_TO}]->(b:{NODE_LABEL} {{user_id: $user_id}})
                WHERE a.id IN $node_ids AND b.id IN $node_ids
                RETURN a.id AS source_id, b.id AS target_id,
                       r.relation AS relation, r.weight AS weight,
                       elementId(r) AS edge_id
                """,
                user_id=user_id,
                node_ids=list(tree_node_ids),
            )
            edges = []
            async for record in edges_result:
                edges.append({
                    "id": record["edge_id"],
                    "source_id": record["source_id"],
                    "target_id": record["target_id"],
                    "relation": record["relation"],
                    "weight": record.get("weight", 1.0),
                })

            return {"book": book, "nodes": tree_nodes, "edges": edges}
