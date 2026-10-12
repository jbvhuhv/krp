from app.core.prompt_manager import prompt_manager


class QuizMixin:
    async def generate_question(self, node_name: str, node_summary: str) -> str:
        prompt = prompt_manager.get_question_prompt(node_name, node_summary)
        response = await self.llm.chat(prompt)
        return response.strip()
