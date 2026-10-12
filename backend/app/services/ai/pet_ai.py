from app.core.prompt_manager import prompt_manager
from app.prompts.pet import PET_CHAT_MAX_TOKENS, PET_CHAT_TEMPERATURE


class PetMixin:
    def build_pet_prompt(
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
        return prompt_manager.get_pet_prompt(
            level=level,
            user_message=user_message,
            knowledge_concepts=knowledge_concepts,
            name=name,
            personality=personality,
            species=species,
            mood=mood,
            history=history,
        )

    async def pet_chat_stream(
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
        temperature: float = PET_CHAT_TEMPERATURE,
        max_tokens: int = PET_CHAT_MAX_TOKENS,
    ):
        prompt = self.build_pet_prompt(
            level,
            user_message,
            knowledge_concepts,
            name=name,
            personality=personality,
            species=species,
            mood=mood,
            history=history,
        )
        async for raw in self.llm.stream_chat(
            prompt, temperature=temperature, max_tokens=max_tokens
        ):
            token = self._parse_stream_token(raw)
            if token:
                yield token
