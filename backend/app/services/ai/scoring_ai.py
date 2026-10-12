import json

from app.core.logger import get_logger
from app.core.prompt_manager import prompt_manager
from app.services.providers.base import LLM_ERROR_TYPES, degraded_result

logger = get_logger(__name__)


class ScoringMixin:
    async def evaluate_answer(
        self, node_name: str, question: str, answer: str
    ) -> dict:
        prompt = prompt_manager.get_evaluation_prompt(node_name, question, answer)
        try:
            response = await self.llm.chat(prompt)
        except LLM_ERROR_TYPES as exc:
            logger.warning("答案评分调用 LLM 失败，触发降级：%s", exc)
            return degraded_result()
        return self._parse_evaluation_response(response)

    @staticmethod
    def _parse_evaluation_response(response: str) -> dict:
        text = response.strip()
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM 评分返回非 JSON，返回默认结果")
            return {
                "concept_accuracy": 0.0,
                "logic_completeness": 0.0,
                "example_reasonableness": 0.0,
                "weak_points": [],
                "suggestion": "评估失败，请重试",
                "resources": [],
            }
        result.setdefault("concept_accuracy", 0.0)
        result.setdefault("logic_completeness", 0.0)
        result.setdefault("example_reasonableness", 0.0)
        result.setdefault("weak_points", [])
        result.setdefault("suggestion", "")
        result.setdefault("resources", [])
        return result
