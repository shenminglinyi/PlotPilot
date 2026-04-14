"""LLM client wrapper with provider auto-selection."""
import os
from typing import Optional, AsyncIterator

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.mock_provider import MockProvider
from infrastructure.ai.providers.openai_provider import OpenAIProvider


class LLMClient:
    """Wrap a provider and offer simple generate helpers."""

    def __init__(self, provider=None):
        if provider:
            self.provider = provider
        else:
            self.provider = self._build_provider()

    def _get_anthropic_api_key(self) -> Optional[str]:
        raw = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        if raw is None:
            return None
        key = raw.strip()
        return key or None

    def _get_anthropic_base_url(self) -> Optional[str]:
        u = os.getenv("ANTHROPIC_BASE_URL")
        return u.strip() if u and u.strip() else None

    def _get_openai_api_key(self) -> Optional[str]:
        raw = os.getenv("OPENAI_API_KEY")
        if raw is None:
            return None
        key = raw.strip()
        return key or None

    def _get_openai_base_url(self) -> Optional[str]:
        u = os.getenv("OPENAI_BASE_URL")
        return u.strip() if u and u.strip() else None

    def _build_provider(self):
        provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

        if provider == "openai":
            api_key = self._get_openai_api_key()
            if api_key:
                return OpenAIProvider(
                    Settings(
                        api_key=api_key,
                        base_url=self._get_openai_base_url(),
                    )
                )
        else:
            api_key = self._get_anthropic_api_key()
            if api_key:
                return AnthropicProvider(
                    Settings(
                        api_key=api_key,
                        base_url=self._get_anthropic_base_url(),
                    )
                )

        return MockProvider()

    async def generate(self, prompt: str, **kwargs) -> str:
        prompt_obj = Prompt(
            system="你是一个专业的小说创作助手。",
            user=prompt,
        )

        config = GenerationConfig(
            model=kwargs.get("model"),
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 1.0),
        )

        result = await self.provider.generate(prompt_obj, config)
        return result.content

    async def stream_generate(
        self,
        prompt,
        config=None,
        **kwargs
    ) -> AsyncIterator[str]:
        if isinstance(prompt, str):
            prompt_obj = Prompt(
                system="你是一个专业的小说创作助手。",
                user=prompt,
            )
        else:
            prompt_obj = prompt

        if config is None:
            config = GenerationConfig(
                model=kwargs.get("model"),
                max_tokens=kwargs.get("max_tokens", 3000),
                temperature=kwargs.get("temperature", 0.85),
            )

        async for chunk in self.provider.stream_generate(prompt_obj, config):
            yield chunk
