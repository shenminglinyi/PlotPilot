from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Optional

from application.ai.llm_control_service import LLMControlService, LLMProfile
from application.ai.trace_context import (
    content_hash,
    ensure_trace,
    preview_text,
    prompt_preview,
    prompt_to_hash_payload,
)
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.gemini_provider import GeminiProvider
from infrastructure.ai.providers.mock_provider import MockProvider
from infrastructure.ai.providers.openai_provider import OpenAIProvider
from infrastructure.ai.trace_recorder import get_trace_recorder
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
        if resolved.protocol == "anthropic":
            return AnthropicProvider(settings)
        if resolved.protocol == "gemini":
            return GeminiProvider(settings)
        return OpenAIProvider(settings)

    def create_active_provider(self) -> LLMService:
        return self.create_from_profile(self.control_service.resolve_active_profile())

    def _profile_to_settings(self, profile: LLMProfile) -> Settings:
        if profile.protocol == "anthropic":
            normalized_base_url = normalize_anthropic_base_url(profile.base_url)
        elif profile.protocol == "gemini":
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
    """生成 Provider 缓存键，配置变化时自动重建 Provider。"""
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
    """动态读取当前激活配置，并在配置不变时复用 Provider。"""

    def __init__(self, factory: Optional[LLMProviderFactory] = None):
        self.factory = factory or LLMProviderFactory()
        self._cached_provider: Optional[LLMService] = None
        self._cached_key: Optional[str] = None

    def _resolve_provider(self) -> LLMService:
        profile = self.factory.control_service.resolve_active_profile()
        key = _make_cache_key(profile) if profile else "__mock__"

        if key == self._cached_key and self._cached_provider is not None:
            return self._cached_provider

        self._close_cached_provider()

        provider = self.factory.create_from_profile(profile)
        self._cached_provider = provider
        self._cached_key = key
        logger.debug(
            "Provider 缓存未命中，创建新实例: protocol=%s model=%s",
            getattr(profile, "protocol", "?"),
            getattr(profile, "model", "?"),
        )
        return provider

    def _close_cached_provider(self) -> None:
        """关闭旧 Provider 的 HTTP 连接资源。"""
        old = self._cached_provider
        if old is None:
            return
        try:
            if hasattr(old, "_http_client_sync") and old._http_client_sync is not None:
                if not old._http_client_sync.is_closed:
                    old._http_client_sync.close()
            for attr in ("_http_client_async", "_http_client", "_stream_http_client"):
                obj = getattr(old, attr, None)
                if obj is not None and hasattr(obj, "is_closed") and not obj.is_closed:
                    setattr(old, attr, None)
        except Exception:
            pass
        self._cached_provider = None
        self._cached_key = None

    @staticmethod
    def _merge_config(config: GenerationConfig, provider: LLMService) -> GenerationConfig:
        settings = getattr(provider, "settings", None)
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
            response_format=config.response_format,
        )

    @staticmethod
    def _request_metadata(
        provider: LLMService,
        effective_config: GenerationConfig,
        *,
        stream: bool = False,
    ) -> tuple[str, str, str, dict]:
        settings = getattr(provider, "settings", None)
        provider_label = provider.__class__.__name__
        generation_profile = getattr(settings, "provider_name", None) or provider_label
        model = effective_config.model or getattr(settings, "default_model", "")
        metadata = {
            "provider": provider_label,
            "protocol": getattr(settings, "protocol", None),
            "base_url": getattr(settings, "base_url", None),
            "temperature": effective_config.temperature,
            "max_tokens": effective_config.max_tokens,
            "response_format": effective_config.response_format,
        }
        if stream:
            metadata["stream"] = True
        return provider_label, generation_profile, model, metadata

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        provider = self._resolve_provider()
        effective_config = self._merge_config(config, provider)
        trace = ensure_trace(operation="llm_generate", metadata={"entry": "DynamicLLMService.generate"})
        request_span_id = trace.new_span_id("llm-request")
        recorder = get_trace_recorder()
        _, generation_profile, model, request_metadata = self._request_metadata(provider, effective_config)

        recorder.record_span(
            phase="llm_request",
            trace_context=trace,
            span_id=request_span_id,
            node_type="llm",
            model=model,
            generation_profile=generation_profile,
            prompt_hash=content_hash(prompt_to_hash_payload(prompt)),
            prompt_preview=prompt_preview(prompt),
            metadata=request_metadata,
        )
        started = time.perf_counter()
        try:
            result = await provider.generate(prompt, effective_config)
        except Exception as exc:
            recorder.record_span(
                phase="error",
                trace_context=trace,
                parent_span_id=request_span_id,
                node_type="llm",
                model=model,
                generation_profile=generation_profile,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
                metadata={**request_metadata, "stage": "provider.generate"},
            )
            raise

        usage = getattr(result, "token_usage", None)
        content = getattr(result, "content", "") or ""
        recorder.record_span(
            phase="llm_response",
            trace_context=trace,
            parent_span_id=request_span_id,
            node_type="llm",
            model=model,
            generation_profile=generation_profile,
            response_hash=content_hash(content),
            response_preview=preview_text(content),
            token_input=getattr(usage, "input_tokens", None),
            token_output=getattr(usage, "output_tokens", None),
            latency_ms=int((time.perf_counter() - started) * 1000),
            metadata={**request_metadata, "content_length": len(content)},
        )
        return result

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        provider = self._resolve_provider()
        effective_config = self._merge_config(config, provider)
        trace = ensure_trace(
            operation="llm_stream_generate",
            metadata={"entry": "DynamicLLMService.stream_generate"},
        )
        request_span_id = trace.new_span_id("llm-stream-request")
        recorder = get_trace_recorder()
        _, generation_profile, model, request_metadata = self._request_metadata(
            provider,
            effective_config,
            stream=True,
        )

        recorder.record_span(
            phase="llm_request",
            trace_context=trace,
            span_id=request_span_id,
            node_type="llm",
            model=model,
            generation_profile=generation_profile,
            prompt_hash=content_hash(prompt_to_hash_payload(prompt)),
            prompt_preview=prompt_preview(prompt),
            metadata=request_metadata,
        )
        started = time.perf_counter()
        response_parts: list[str] = []
        preview_parts: list[str] = []
        preview_chars = 0
        total_chars = 0
        try:
            async for chunk in provider.stream_generate(prompt, effective_config):
                if chunk:
                    response_parts.append(chunk)
                    total_chars += len(chunk)
                    if preview_chars < 320:
                        preview_parts.append(chunk)
                        preview_chars += len(chunk)
                yield chunk
        except Exception as exc:
            recorder.record_span(
                phase="error",
                trace_context=trace,
                parent_span_id=request_span_id,
                node_type="llm",
                model=model,
                generation_profile=generation_profile,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
                metadata={**request_metadata, "stage": "provider.stream_generate"},
            )
            raise
        else:
            content_for_hash = "".join(response_parts)
            recorder.record_span(
                phase="llm_response",
                trace_context=trace,
                parent_span_id=request_span_id,
                node_type="llm",
                model=model,
                generation_profile=generation_profile,
                response_hash=content_hash(content_for_hash),
                response_preview=preview_text("".join(preview_parts)),
                latency_ms=int((time.perf_counter() - started) * 1000),
                metadata={**request_metadata, "content_length": total_chars},
            )

    async def aclose(self) -> None:
        """异步关闭缓存 Provider。"""
        old = self._cached_provider
        if old is None:
            return
        try:
            if hasattr(old, "aclose"):
                await old.aclose()
        except Exception as exc:
            logger.debug("关闭 Provider 时出现可忽略异常: %s", exc)
        finally:
            self._cached_provider = None
            self._cached_key = None
