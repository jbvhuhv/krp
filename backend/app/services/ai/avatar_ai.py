from app.core.prompt_manager import prompt_manager


class AvatarMixin:
    async def avatar_chat(self, query: str, context: str) -> str:
        ...

    def build_avatar_prompt(
        self,
        query: str,
        context: str,
        tone: str = "rigorous",
        history: list[dict] | None = None,
    ) -> str:
        return prompt_manager.get_avatar_prompt(
            query=query, context=context, tone=tone, history=history
        )

    def build_avatar_smalltalk_prompt(
        self,
        query: str,
        tone: str = "rigorous",
        history: list[dict] | None = None,
    ) -> str:
        return prompt_manager.get_avatar_smalltalk_prompt(
            query=query, tone=tone, history=history
        )

    async def avatar_chat_stream(
        self,
        query: str,
        context: str,
        tone: str = "rigorous",
        history: list[dict] | None = None,
    ):
        prompt = self.build_avatar_prompt(query, context, tone=tone, history=history)
        async for raw in self.llm.stream_chat(prompt):
            token = self._parse_stream_token(raw)
            if token:
                yield token

    async def avatar_smalltalk_stream(
        self,
        query: str,
        tone: str = "rigorous",
        history: list[dict] | None = None,
    ):
        prompt = self.build_avatar_smalltalk_prompt(query, tone=tone, history=history)
        async for raw in self.llm.stream_chat(prompt):
            token = self._parse_stream_token(raw)
            if token:
                yield token
