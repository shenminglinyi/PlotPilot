from typing import AsyncIterator

import pytest

from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.provider_factory import ProfilePinnedLLMService


class _RecordingProvider(LLMService):
    def __init__(self):
        self.configs: list[GenerationConfig] = []

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        self.configs.append(config)
        return GenerationResult("ok", TokenUsage(input_tokens=1, output_tokens=1))

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        self.configs.append(config)
        yield "ok"


class _RecordingFactory:
    def __init__(self):
        self.profile_ids: list[str] = []
        self.provider = _RecordingProvider()

    def create_by_profile_id(self, profile_id: str) -> LLMService:
        self.profile_ids.append(profile_id)
        return self.provider

    def create_active_provider(self) -> LLMService:
        self.profile_ids.append("active")
        return self.provider


@pytest.mark.asyncio
async def test_profile_pinned_llm_service_uses_target_profile_and_preserves_response_format():
    factory = _RecordingFactory()
    service = ProfilePinnedLLMService(factory, profile_id="kimi-moonshot-default", role_name="writing")

    await service.generate(
        Prompt(system="system", user="user"),
        GenerationConfig(max_tokens=32, temperature=0.4, response_format={"type": "json_object"}),
    )

    assert factory.profile_ids == ["kimi-moonshot-default"]
    assert factory.provider.configs[0].response_format == {"type": "json_object"}
