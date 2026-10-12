from app.services.graph.constants import NODE_LABEL


class VectorMixin:
    async def set_node_embedding(
        self, user_id: str, node_id: str, embedding: list[float]
    ) -> None:
        async with self.driver.session() as session:
            await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{id: $node_id, user_id: $user_id}})
                SET n.embedding = $embedding
                """,
                node_id=node_id,
                user_id=user_id,
                embedding=embedding,
            )

    async def get_nodes_without_embedding(
        self, user_id: str, limit: int = 200
    ) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                WHERE n.embedding IS NULL
                RETURN n
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            nodes = []
            async for record in result:
                nodes.append(dict(record["n"]))
            return nodes

    async def vector_search(
        self,
        user_id: str,
        embedding: list[float],
        top_k: int = 5,
        index_name: str = "knowledge_node_embedding",
    ) -> list[dict]:
        # 向量索引是全局的（跨用户），且当前 Neo4j 版本不支持索引级过滤，
        # 因此只能先召回再按 user_id 过滤。为避免「自己节点排在 fetch_k 之外」
        # 导致的召回饥饿，命中不足时按倍数扩大召回窗口，直到满足 top_k 或达到上限。
        fetch_k = max(top_k * 10, top_k)
        max_fetch = max(top_k * 200, 1000)
        async with self.driver.session() as session:
            while True:
                result = await session.run(
                    f"""
                    CALL db.index.vector.queryNodes('{index_name}', $fetch_k, $embedding)
                    YIELD node, score
                    WHERE node.user_id = $user_id
                    RETURN node, score
                    ORDER BY score DESC
                    LIMIT $top_k
                    """,
                    fetch_k=fetch_k,
                    embedding=embedding,
                    user_id=user_id,
                    top_k=top_k,
                )
                hits = []
                async for record in result:
                    hits.append({
                        "node": dict(record["node"]),
                        "score": float(record["score"]),
                    })
                if len(hits) >= top_k or fetch_k >= max_fetch:
                    return hits
                fetch_k = min(fetch_k * 4, max_fetch)

    @staticmethod
    def _char_bigrams(text: str) -> set[str]:
        cleaned = "".join(
            ch for ch in (text or "").lower() if ch.isalnum()
        )
        if not cleaned:
            return set()
        if len(cleaned) < 2:
            return {cleaned}
        return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}

    async def keyword_search(
        self, user_id: str, query: str, top_k: int = 5
    ) -> list[dict]:
        query_grams = self._char_bigrams(query)
        if not query_grams:
            return []
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                RETURN n
                """,
                user_id=user_id,
            )
            hits = []
            async for record in result:
                node = dict(record["n"])
                text = f"{node.get('name', '')} {node.get('summary', '')}"
                grams = self._char_bigrams(text)
                if not grams:
                    continue
                overlap = len(query_grams & grams)
                if overlap == 0:
                    continue
                hits.append({
                    "node": node,
                    "score": overlap / min(len(query_grams), len(grams)),
                })
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:top_k]
