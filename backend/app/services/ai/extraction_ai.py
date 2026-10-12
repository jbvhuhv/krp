import json

from app.core.logger import get_logger
from app.core.prompt_manager import prompt_manager
from app.services.providers.base import LLM_ERROR_TYPES, degraded_result

logger = get_logger(__name__)


class ExtractionMixin:
    async def extract_knowledge(self, text: str) -> dict:
        prompt = prompt_manager.get_extraction_prompt(text)
        try:
            response = await self.llm.chat(prompt)
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
            return {"categories": [], "edges": [], "book_summary": ""}
        result.setdefault("categories", [])
        result.setdefault("edges", [])
        result.setdefault("book_summary", "")
        result.setdefault("subject", "")
        result.setdefault("nodes", [])
        return result
