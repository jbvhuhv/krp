"""提示词管理器（PromptManager）。

业务层统一通过单例 ``prompt_manager`` 获取已格式化的 Prompt，避免 Prompt 文本
散落在各 service 中；所有模板集中在 ``app.prompts`` 包内维护与版本化。
"""

from __future__ import annotations

from app.prompts import avatar as avatar_prompts
from app.prompts import brainstorm as brainstorm_prompts
from app.prompts import common as common_prompts
from app.prompts import extraction as extraction_prompts
from app.prompts import ocr as ocr_prompts
from app.prompts import pet as pet_prompts
from app.prompts import reflection as reflection_prompts

MAX_EXTRACTION_CHARS = 8000
MAX_HISTORY_TURNS = 6


class PromptManager:
    """集中式 Prompt 装配器。"""

    version = common_prompts.PROMPT_VERSION

    def get_injection_guard(self) -> str:
        """返回防注入声明原文，供需要自行拼接的场景复用。"""
        return common_prompts.INJECTION_GUARD

    # ------------------------------------------------------------------ 抽取
    def get_extraction_template(self) -> str:
        return extraction_prompts.EXTRACTION_PROMPT

    def get_extraction_prompt(self, text: str) -> str:
        trimmed = (text or "")[:MAX_EXTRACTION_CHARS]
        return extraction_prompts.EXTRACTION_PROMPT.format(
            text=common_prompts.sanitize_user_input(trimmed)
        )

    # ---------------------------------------------------------- 图片 OCR
    def get_ocr_prompt(self) -> str:
        return ocr_prompts.OCR_PROMPT

    # ---------------------------------------------------------- 反思：问答
    def get_question_prompt(self, node_name: str, node_summary: str) -> str:
        return reflection_prompts.QUESTION_GENERATION_PROMPT.format(
            node_name=node_name,
            node_summary=node_summary or "无摘要",
        )

    def get_evaluation_prompt(
        self, node_name: str, question: str, answer: str
    ) -> str:
        return reflection_prompts.EVALUATION_PROMPT.format(
            node_name=node_name or "未知知识点",
            question=question,
            answer=common_prompts.sanitize_user_input(answer),
        )

    # -------------------------------------------------------------- 数字分身
    def get_avatar_prompt(
        self,
        query: str,
        context: str,
        tone: str = "rigorous",
        history: list[dict] | None = None,
    ) -> str:
        return avatar_prompts.AVATAR_CHAT_PROMPT.format(
            tone_desc=self._tone_desc(tone),
            context=context or "（知识库暂无可检索内容）",
            history=self._format_history(history),
            query=common_prompts.sanitize_user_input(query),
        )

    def get_avatar_smalltalk_prompt(
        self,
        query: str,
        tone: str = "rigorous",
        history: list[dict] | None = None,
    ) -> str:
        return avatar_prompts.AVATAR_SMALLTALK_PROMPT.format(
            tone_desc=self._tone_desc(tone),
            history=self._format_history(history),
            query=common_prompts.sanitize_user_input(query),
        )

    # ------------------------------------------------------------------ 宠物
    def get_pet_prompt(
        self,
        level: int,
        user_message: str,
        knowledge_concepts: list[str] | None = None,
        *,
        name: str | None = None,
        personality: str | None = None,
        species: str | None = None,
        mood: str | None = None,
        history: list[dict] | None = None,
    ) -> str:
        prompts = pet_prompts.PET_SYSTEM_PROMPTS
        if level < 3:
            tier_prompt = prompts["baby"]
        elif level < 8:
            concepts_text = (
                "、".join(knowledge_concepts[:5])
                if knowledge_concepts
                else "各种知识"
            )
            tier_prompt = prompts["growing"].format(concepts=concepts_text)
        else:
            concepts_text = (
                "、".join(knowledge_concepts[:5])
                if knowledge_concepts
                else "你最近所学的知识"
            )
            tier_prompt = prompts["wise"].replace(
                "A和B", concepts_text[:20] + "等概念"
            )
        # 注入独特的身份（名字/物种/性格）与当下情绪，形成稳定且个性化的人设
        persona = pet_prompts.build_persona(name, species, personality, mood)
        system_prompt = f"{persona}\n{tier_prompt}" if persona else tier_prompt
        return pet_prompts.PET_CHAT_PROMPT.format(
            system_prompt=system_prompt,
            history_block=self._format_pet_history(history),
            user_message=common_prompts.sanitize_user_input(user_message),
        )

    # ------------------------------------------------------ 节点 / 目录摘要
    def get_node_summary_prompt(
        self, node_name: str, node_summary: str, child_info: str
    ) -> str:
        return common_prompts.NODE_SUMMARY_PROMPT.format(
            node_name=node_name,
            node_summary=node_summary or "无",
            child_info=child_info,
        )

    def get_category_summary_prompt(self, node_name: str, child_info: str) -> str:
        return common_prompts.CATEGORY_SUMMARY_PROMPT.format(
            node_name=node_name,
            child_info=child_info,
        )

    # ---------------------------------------------------------- AI 辅助手绘
    def get_brainstorm_verify_prompt(self, tree_text: str) -> str:
        return brainstorm_prompts.BRAINSTORM_VERIFY_PROMPT.format(
            tree_text=common_prompts.sanitize_user_input(tree_text, max_len=4000)
        )

    def get_brainstorm_hint_prompt(
        self, node_name: str, node_summary: str
    ) -> str:
        return brainstorm_prompts.BRAINSTORM_HINT_PROMPT.format(
            node_name=node_name,
            node_summary=node_summary or "无",
        )

    def get_brainstorm_guide_prompt(self, node_name: str, user_idea: str) -> str:
        return brainstorm_prompts.BRAINSTORM_GUIDE_PROMPT.format(
            node_name=node_name,
            user_idea=common_prompts.sanitize_user_input(user_idea),
        )

    def get_brainstorm_generate_prompt(
        self, node_name: str, node_summary: str
    ) -> str:
        return brainstorm_prompts.BRAINSTORM_GENERATE_PROMPT.format(
            node_name=node_name,
            node_summary=node_summary or "无",
        )

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _tone_desc(tone: str) -> str:
        return avatar_prompts.TONE_DESCRIPTIONS.get(
            tone, avatar_prompts.TONE_DESCRIPTIONS["rigorous"]
        )

    @staticmethod
    def _format_pet_history(history: list[dict] | None) -> str:
        """把宠物对话历史拼成上下文块；无历史时返回空串。"""
        if not history:
            return ""
        lines = []
        for turn in history[-MAX_HISTORY_TURNS:]:
            role = "主人" if turn.get("role") == "user" else "你"
            content = common_prompts.sanitize_user_input(turn.get("content", ""))
            if content:
                lines.append(f"{role}：{content}")
        if not lines:
            return ""
        return "\n\n最近你和主人的对话（越靠后越新，请自然接续，不要复述）：\n" + "\n".join(
            lines
        )

    @staticmethod
    def _format_history(history: list[dict] | None) -> str:
        if not history:
            return "无"
        lines = []
        for turn in history[-MAX_HISTORY_TURNS:]:
            role = "访客" if turn.get("role") == "user" else "分身"
            content = common_prompts.sanitize_user_input(turn.get("content", ""))
            lines.append(f"{role}：{content}")
        return "\n".join(lines)


prompt_manager = PromptManager()
