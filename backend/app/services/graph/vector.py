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

    async def get_nodes_missing_embedding_by_note(
        self, user_id: str, note_id: str, limit: int = 200
    ) -> list[dict]:
        """取某次抽取产生的、尚无向量的节点。

        抽取链路用这个方法只为"本次新写的节点"补向量，
        不会把历史遗留的无向量节点一起算进来（那是发布回填的职责）。
        """
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id, source_note_id: $note_id}})
                WHERE n.embedding IS NULL
                RETURN n
                LIMIT $limit
                """,
                user_id=user_id,
                note_id=note_id,
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

    @classmethod
    def keyword_score(cls, query: str, text: str) -> float:
        """查询与文本的字面重叠度（0~1）。

        单字查询（"力""熵"）走子串匹配：二元组永远匹配不上二元组，
        否则用户问「什么是力」会得到 0 命中，而库里明明有「力学性能基础」。
        """
        q = "".join(ch for ch in (query or "").lower() if ch.isalnum())
        t = "".join(ch for ch in (text or "").lower() if ch.isalnum())
        if not q or not t:
            return 0.0
        if len(q) == 1:
            return 1.0 if q in t else 0.0
        q_grams = {q[i : i + 2] for i in range(len(q) - 1)}
        t_grams = {t[i : i + 2] for i in range(len(t) - 1)}
        if not q_grams or not t_grams:
            return 0.0
        # 分母固定为查询侧：文本再长也不会把「部分命中」抬成满分
        return len(q_grams & t_grams) / len(q_grams)

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
                score = self.keyword_score(query, text)
                if score <= 0:
                    continue
                hits.append({"node": node, "score": score})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:top_k]
