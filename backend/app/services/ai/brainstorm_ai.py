import json

from app.core.logger import get_logger
from app.core.prompt_manager import prompt_manager
from app.services.providers.base import LLM_ERROR_TYPES, degraded_result

logger = get_logger(__name__)

# Provider 未配置时抛 RuntimeError（不在 LLM_ERROR_TYPES 内），一并降级处理。
_ERROR_TYPES = LLM_ERROR_TYPES + (RuntimeError,)


class BrainstormMixin:
    async def verify_structure(self, tree_text: str) -> dict:
        prompt = prompt_manager.get_brainstorm_verify_prompt(tree_text)
        try:
            response = await self.llm.chat(prompt)
        except _ERROR_TYPES as exc:
            logger.warning("结构校验调用 LLM 失败，触发降级：%s", exc)
            return degraded_result(overall="", issues=[], missing=[])
        return self._parse_json(response, {"overall": "", "issues": [], "missing": []})

    async def suggest_hint(self, node_name: str, node_summary: str) -> dict:
        prompt = prompt_manager.get_brainstorm_hint_prompt(node_name, node_summary)
        try:
            response = await self.llm.chat(prompt)
        except _ERROR_TYPES as exc:
            logger.warning("辅助构思调用 LLM 失败，触发降级：%s", exc)
            return degraded_result(suggestions=[])
        return self._parse_json(response, {"suggestions": []})

    async def guide_idea(self, node_name: str, user_idea: str) -> dict:
        prompt = prompt_manager.get_brainstorm_guide_prompt(node_name, user_idea)
        try:
            response = await self.llm.chat(prompt)
        except _ERROR_TYPES as exc:
            logger.warning("想法引导调用 LLM 失败，触发降级：%s", exc)
            return degraded_result(guidance="")
        return self._parse_json(response, {"guidance": ""})

    async def generate_subtree(self, node_name: str, node_summary: str) -> dict:
        prompt = prompt_manager.get_brainstorm_generate_prompt(node_name, node_summary)
        try:
            response = await self.llm.chat(prompt)
        except _ERROR_TYPES as exc:
            logger.warning("子树生成调用 LLM 失败，触发降级：%s", exc)
            return degraded_result(nodes=[])
        return self._parse_json(response, {"nodes": []})

    @staticmethod
    def _parse_json(response: str, default: dict) -> dict:
        text = (response or "").strip()
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
            logger.warning("LLM 返回非 JSON 内容，使用默认结果")
            return dict(default)
        if not isinstance(result, dict):
            return dict(default)
        for key, value in default.items():
            result.setdefault(key, value)
        return result
