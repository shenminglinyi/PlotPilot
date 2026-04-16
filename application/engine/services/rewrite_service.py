from typing import AsyncIterator, List, Optional

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.llm_client import LLMClient

MODE_PROMPTS = {
    "rewrite": "请改写以下文字，保持原意但换一种表达方式，使文字更生动、更有文学性",
    "expand": "请扩写以下文字，增加细节描写、环境烘托、心理活动等，使内容更丰富饱满",
    "shrink": "请缩写以下文字，保留核心情节和关键信息，删减冗余描写",
    "polish": "请润色以下文字，修正语病、优化句式、提升文学性，但不改变原意",
    "continue": "请续写以下文字，保持文风和叙事节奏一致，自然衔接",
}


class RewriteService:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    async def rewrite(self, text: str, mode: str, context: str = "") -> str:
        if mode not in MODE_PROMPTS:
            raise ValueError(f"Unsupported mode: {mode}")
        system_prompt = MODE_PROMPTS[mode]
        user_parts: List[str] = []
        if context.strip():
            user_parts.append(f"前文上下文：\n{context.strip()}")
        user_parts.append(f"原文：\n{text.strip()}")
        user_prompt = "\n\n".join(user_parts)
        prompt = Prompt(system=system_prompt, user=user_prompt)
        config = GenerationConfig(temperature=0.7)
        result = await self.llm_client.provider.generate(prompt, config)
        return result.content

    async def stream_rewrite(self, text: str, mode: str, context: str = "") -> AsyncIterator[str]:
        if mode not in MODE_PROMPTS:
            raise ValueError(f"Unsupported mode: {mode}")
        system_prompt = MODE_PROMPTS[mode]
        user_parts: List[str] = []
        if context.strip():
            user_parts.append(f"前文上下文：\n{context.strip()}")
        user_parts.append(f"原文：\n{text.strip()}")
        user_prompt = "\n\n".join(user_parts)
        prompt = Prompt(system=system_prompt, user=user_prompt)
        config = GenerationConfig(temperature=0.7)
        async for chunk in self.llm_client.provider.stream_generate(prompt, config):
            yield chunk
