import json

from app.core.logger import get_logger
from app.core.prompt_manager import prompt_manager
from app.services.providers.base import (
    LLM_ERROR_TYPES,
    degraded_result,
    json_call_kwargs,
)

logger = get_logger(__name__)


class ExtractionMixin:
    async def extract_knowledge(self, text: str) -> dict:
        prompt = prompt_manager.get_extraction_prompt(text)
        try:
            response = await self.llm.chat(prompt, **json_call_kwargs())
        except LLM_ERROR_TYPES as exc:
            logger.warning("知识抽取调用 LLM 失败，触发降级：%s", exc)
            return degraded_result(
                categories=[], edges=[], book_summary="", subject="", nodes=[]
            )
        return self._parse_extraction_response(response)

    @staticmethod
    def _parse_extraction_response(response: str) -> dict:
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
            logger.warning("LLM 返回非 JSON 内容，返回空结果")
            # 注意：不要在这里直接 return 一个「少几个 key」的字典。
            # 解析失败与解析成功必须返回同一套字段，否则下游按成功路径取 result["nodes"]
            # 时会在「模型偶尔胡说」这种最常见的场景下抛 KeyError，把可控降级变成 500。
            result = {}
        result.setdefault("categories", [])
        result.setdefault("edges", [])
        result.setdefault("book_summary", "")
        result.setdefault("subject", "")
        result.setdefault("nodes", [])
        return result
