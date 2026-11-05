import json

from app.core.logger import get_logger
from app.core.prompt_manager import prompt_manager
from app.services.providers.base import (
    LLM_ERROR_TYPES,
    degraded_result,
    json_call_kwargs,
)

logger = get_logger(__name__)


class ScoringMixin:
    async def evaluate_answer(
        self, node_name: str, question: str, answer: str
    ) -> dict:
        prompt = prompt_manager.get_evaluation_prompt(node_name, question, answer)
        try:
            # temperature=0：同一份答案重复提交必须得到同一个分数，
            # 否则掌握度（EMA 融合）会被随机分数污染。
            response = await self.llm.chat(prompt, **json_call_kwargs())
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
        result.setdefault("key_points", [])
        # 模型偶尔把数组写成字符串（"1. xx 2. yy"），统一收敛成 list[str]，
        # 否则前端 v-for 会渲染成一串字符，落库时也会序列化出意外的形状。
        result["weak_points"] = _as_str_list(result["weak_points"])
        result["resources"] = _as_str_list(result["resources"])
        result["key_points"] = _as_str_list(result["key_points"])[:5]
        if not isinstance(result["suggestion"], str):
            result["suggestion"] = str(result["suggestion"] or "")
        return result


def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip(" -·\t") for p in value.replace("；", "\n").splitlines()]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]
