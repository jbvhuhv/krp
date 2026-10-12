from app.services.graph.constants import (
    NODE_LABEL,
    NODE_TYPE_KNOWLEDGE,
    NOISE_SUBJECTS,
    UNCLASSIFIED_SUBJECT,
)


class StatsMixin:
    async def get_subject_distribution(self, user_id: str) -> dict[str, int]:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id}})
                WITH coalesce(n.subject, $unclassified) AS subject
                RETURN subject AS subject, count(*) AS cnt
                """,
                user_id=user_id,
                unclassified=UNCLASSIFIED_SUBJECT,
            )
            distribution: dict[str, int] = {}
            async for record in result:
                distribution[record["subject"]] = record["cnt"]
            return distribution

    async def get_mastery_overview(self, user_id: str) -> dict:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id, node_type: $node_type}})
                WITH coalesce(n.mastery, 0.0) AS mastery
                RETURN count(mastery) AS total,
                       coalesce(avg(mastery), 0.0) AS avg_mastery,
                       sum(CASE WHEN mastery < 60 THEN 1 ELSE 0 END) AS weak,
                       sum(CASE WHEN mastery >= 60 AND mastery < 80 THEN 1 ELSE 0 END) AS basic,
                       sum(CASE WHEN mastery >= 80 THEN 1 ELSE 0 END) AS proficient
                """,
                user_id=user_id,
                node_type=NODE_TYPE_KNOWLEDGE,
            )
            record = await result.single()
        total = int(record["total"]) if record else 0
        if total == 0:
            return {
                "total": 0,
                "avg_mastery": 0.0,
                "weak": 0,
                "basic": 0,
                "proficient": 0,
            }
        return {
            "total": total,
            "avg_mastery": float(record["avg_mastery"] or 0.0),
            "weak": int(record["weak"] or 0),
            "basic": int(record["basic"] or 0),
            "proficient": int(record["proficient"] or 0),
        }

    async def get_subject_stats(self, user_id: str) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{NODE_LABEL} {{user_id: $user_id, node_type: $node_type}})
                WITH coalesce(n.subject, $unclassified) AS subject,
                     coalesce(n.mastery, 0.0) AS mastery
                WHERE NOT subject IN $noise_subjects
                RETURN subject AS subject,
                       count(*) AS node_count,
                       avg(mastery) AS avg_mastery
                ORDER BY node_count DESC, subject ASC
                """,
                user_id=user_id,
                node_type=NODE_TYPE_KNOWLEDGE,
                unclassified=UNCLASSIFIED_SUBJECT,
                noise_subjects=list(NOISE_SUBJECTS),
            )
            stats: list[dict] = []
            async for record in result:
                stats.append(
                    {
                        "subject": record["subject"],
                        "node_count": int(record["node_count"]),
                        "avg_mastery": float(record["avg_mastery"] or 0.0),
                    }
                )
            return stats
