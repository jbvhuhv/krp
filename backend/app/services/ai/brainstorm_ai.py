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

    async def guide_idea_stream(self, node_name: str, user_idea: str):
        prompt = prompt_manager.get_brainstorm_guide_stream_prompt(node_name, user_idea)
        try:
            async for chunk in self.llm.stream_chat(prompt):
                text = chunk.strip()
                if not text or text == "[DONE]":
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content") or ""
                if content:
                    yield content
        except _ERROR_TYPES as exc:
            # 不要在这里吞掉：流式接口已经把 200 发出去了，若这里静默结束，
            # 客户端只会收到一个空的 delta 流，最终显示「暂无建议，换个方向试试」——
            # 用户以为模型没想法，实际是调用失败，且额度已经花了。交给上层发 error 帧。
            logger.warning("想法引导流式调用 LLM 失败：%s", exc)
            raise

    async def generate_subtree(self, node_name: str, node_summary: str, existing_children: str = "") -> dict:
        prompt = prompt_manager.get_brainstorm_generate_prompt(node_name, node_summary, existing_children)
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
