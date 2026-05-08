from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

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
logger = logging.getLogger(__name__)


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


def _make_cache_key(profile: LLMProfile) -> str:
    """生成 Provider 缓存键：协议 + base_url + model + api_key（前 8 位）+ temperature + max_tokens。

    当用户在前台切换模型/API Key 时，缓存键变化，自动创建新 Provider；
    同一配置连续调用时复用旧 Provider 及其 HTTP 连接池。
    """
    key_parts = [
        profile.protocol or "",
        (profile.base_url or "").rstrip("/"),
        (profile.model or "").strip(),
        (profile.api_key or "")[:8],
        str(profile.temperature),
        str(profile.max_tokens),
        str(profile.timeout_seconds),
        str(profile.use_legacy_chat_completions),
    ]
    return "|".join(key_parts)


class DynamicLLMService(LLMService):
    """动态读取当前激活配置，适配长生命周期服务/守护进程。

    改进：缓存上一次 resolve 的 Provider 实例，配置不变时复用（避免每次调用重建 httpx client）。
    配置变更时自动创建新 Provider 并关闭旧实例的 HTTP 连接池。
    """

    def __init__(self, factory: Optional[LLMProviderFactory] = None):
        self.factory = factory or LLMProviderFactory()
        self._cached_provider: Optional[LLMService] = None
        self._cached_key: Optional[str] = None

    def _resolve_provider(self) -> LLMService:
        profile = self.factory.control_service.resolve_active_profile()
        key = _make_cache_key(profile) if profile else "__mock__"

        if key == self._cached_key and self._cached_provider is not None:
            return self._cached_provider

        # 配置变更：关闭旧 Provider 的 HTTP 连接池
        self._close_cached_provider()

        provider = self.factory.create_from_profile(profile)
        self._cached_provider = provider
        self._cached_key = key
        logger.debug("Provider 缓存未命中，创建新实例: protocol=%s model=%s",
                      getattr(profile, 'protocol', '?'), getattr(profile, 'model', '?'))
        return provider

    def _close_cached_provider(self) -> None:
        """关闭旧缓存 Provider 的 HTTP 连接池，释放系统资源。"""
        old = self._cached_provider
        if old is None:
            return
        try:
            # 同步关闭 httpx.Client
            if hasattr(old, '_http_client_sync') and old._http_client_sync is not None:
                if not old._http_client_sync.is_closed:
                    old._http_client_sync.close()
            # 异步 client 标记为待 GC（无法在同步上下文中 await aclose）
            for attr in ('_http_client_async', '_http_client', '_stream_http_client'):
                obj = getattr(old, attr, None)
                if obj is not None and hasattr(obj, 'is_closed') and not obj.is_closed:
                    setattr(old, attr, None)
        except Exception:
            pass
        self._cached_provider = None
        self._cached_key = None

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

    async def aclose(self) -> None:
        """异步关闭缓存的 Provider（含 HTTP 连接池）。"""
        old = self._cached_provider
        if old is None:
            return
        try:
            if hasattr(old, 'aclose'):
                await old.aclose()
        except Exception as e:
            logger.debug("关闭 Provider 时异常（可忽略）: %s", e)
        finally:
            self._cached_provider = None
            self._cached_key = None
