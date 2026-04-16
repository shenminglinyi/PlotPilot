from __future__ import annotations

from typing import AsyncIterator

from application.ai.llm_control_service import LLMControlService, LLMProfile
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.gemini_provider import GeminiProvider
from infrastructure.ai.providers.mock_provider import MockProvider
from infrastructure.ai.providers.openai_provider import OpenAIProvider
from infrastructure.ai.url_utils import (
    normalize_anthropic_base_url,
    normalize_gemini_base_url,
    normalize_openai_base_url,
)

_DEFAULT_CONFIG = GenerationConfig()


class LLMProviderFactory:
    def __init__(self, control_service: Optional[LLMControlService] = None):
        self.control_service = control_service or LLMControlService()

    def create_from_profile(self, profile: Optional[LLMProfile]) -> LLMService:
        if profile is None:
            return MockProvider()

        resolved = self.control_service.resolve_profile(profile)
        if not resolved.api_key.strip() or not resolved.model.strip():
            return MockProvider()

        settings = self._profile_to_settings(resolved)
        if resolved.protocol == 'anthropic':
            return AnthropicProvider(settings)
        if resolved.protocol == 'gemini':
            return GeminiProvider(settings)
        return OpenAIProvider(settings)

    def create_active_provider(self) -> LLMService:
        return self.create_from_profile(self.control_service.resolve_active_profile())

    def _profile_to_settings(self, profile: LLMProfile) -> Settings:
        if profile.protocol == 'anthropic':
            normalized_base_url = normalize_anthropic_base_url(profile.base_url)
        elif profile.protocol == 'gemini':
            normalized_base_url = normalize_gemini_base_url(profile.base_url)
        else:
            normalized_base_url = normalize_openai_base_url(profile.base_url)

        return Settings(
            default_model=profile.model,
            default_temperature=profile.temperature,
            default_max_tokens=profile.max_tokens,
            api_key=profile.api_key,
            base_url=normalized_base_url,
            timeout_seconds=profile.timeout_seconds,
            extra_headers=profile.extra_headers,
            extra_query=profile.extra_query,
            extra_body=profile.extra_body,
            provider_name=profile.name,
            protocol=profile.protocol,
            use_legacy_chat_completions=profile.use_legacy_chat_completions,
        )


class DynamicLLMService(LLMService):
    """动态读取当前激活配置，适配长生命周期服务/守护进程。"""

    def __init__(self, factory: Optional[LLMProviderFactory] = None):
        self.factory = factory or LLMProviderFactory()

    def _resolve_provider(self) -> LLMService:
        return self.factory.create_active_provider()

    @staticmethod
    def _merge_config(config: GenerationConfig, provider: LLMService) -> GenerationConfig:
        settings = getattr(provider, 'settings', None)
        if settings is None:
            return config

        model = config.model
        if not model or model == _DEFAULT_CONFIG.model:
            model = settings.default_model

        max_tokens = config.max_tokens
        if max_tokens == _DEFAULT_CONFIG.max_tokens:
            max_tokens = settings.default_max_tokens

        temperature = config.temperature
        if temperature == _DEFAULT_CONFIG.temperature:
            temperature = settings.default_temperature

        return GenerationConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        provider = self._resolve_provider()
        effective_config = self._merge_config(config, provider)
        return await provider.generate(prompt, effective_config)

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        provider = self._resolve_provider()
        effective_config = self._merge_config(config, provider)
        async for chunk in provider.stream_generate(prompt, effective_config):
            yield chunk
