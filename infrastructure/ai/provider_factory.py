from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from typing import AsyncIterator, Literal, Optional

from application.ai.llm_control_service import LLMControlService, LLMProfile
from application.ai.trace_context import (
    TraceContext,
    content_hash,
    ensure_trace,
    get_current_trace,
    get_scoped_prompt_node_key,
    preview_text,
    prompt_preview,
    prompt_to_hash_payload,
)
from domain.ai.errors import LLMNotConfiguredError
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.gemini_provider import GeminiProvider
from infrastructure.ai.providers.openai_provider import OpenAIProvider
from infrastructure.ai.trace_recorder import get_trace_recorder
from infrastructure.ai.url_utils import (
    normalize_anthropic_base_url,
    normalize_gemini_base_url,
    normalize_openai_base_url,
)

_DEFAULT_CONFIG = GenerationConfig()
logger = logging.getLogger(__name__)

LLMRole = Literal["main", "cheap", "kg"]

KG_ROLE_NODE_KEYS: frozenset[str] = frozenset(
    {
        "knowledge-initial",
        "kg-inference",
        "chapter-narrative-sync",
        "chapter-state-extraction",
        "prop-event-extraction",
        "memory-extraction",
        "emotion-ledger-extraction",
        "chapter-bridge-extract",
        "anti-ai-character-state-lock",
    }
)

CHEAP_ROLE_NODE_KEYS: frozenset[str] = frozenset(
    {
        "chapter-summarizer",
        "summary-checkpoint",
        "summary-act",
        "summary-volume",
        "summary-part",
        "tension-scoring",
        "tension-analysis-diagnosis",
        "cliche-scan",
        "chapter-bridge-check",
        "foreshadow-check",
        "style-analysis",
        "voice-drift",
        "anti-ai-allowlist-explain",
        "anti-ai-chapter-audit",
        "review-character-consistency",
        "review-timeline-consistency",
        "review-storyline-consistency",
        "review-foreshadowing-usage",
    }
)


def classify_llm_role(
    prompt: Optional[Prompt] = None,
    config: Optional[GenerationConfig] = None,
    trace: Optional[TraceContext] = None,
) -> LLMRole:
    """Deterministic L3 role classification (main / cheap / kg)."""
    hint = (getattr(config, "role_hint", "") or "").strip()
    if hint in ("main", "cheap", "kg"):
        return hint  # type: ignore[return-value]

    prompt_key = (getattr(prompt, "node_key", "") or "").strip()
    scoped_key = (get_scoped_prompt_node_key() or "").strip()
    node_key = prompt_key or scoped_key
    if node_key:
        if node_key in KG_ROLE_NODE_KEYS:
            return "kg"
        if node_key in CHEAP_ROLE_NODE_KEYS:
            return "cheap"
        return "main"

    effective_trace = trace if trace is not None else get_current_trace()
    stage = (getattr(effective_trace, "stage", "") or "").strip()
    if stage:
        if stage.startswith(("knowledge.", "kg.")):
            return "kg"
        if stage.startswith(("summary.", "analyst.tension.", "audit.chapter.review")):
            return "cheap"

    return "main"


class LLMProviderFactory:
    def __init__(self, control_service: Optional[LLMControlService] = None):
        self.control_service = control_service or LLMControlService()

    def create_from_resolved_profile(self, resolved: Optional[LLMProfile]) -> LLMService:
        if resolved is None:
            raise LLMNotConfiguredError(
                "未找到任何 LLM 配置：请在前台「LLM 控制」中添加并激活一个模型档案"
            )
        if not resolved.api_key.strip() or not resolved.model.strip():
            raise LLMNotConfiguredError(
                f"当前激活配置「{resolved.name}」缺少 API Key 或模型名，无法创建 Provider；"
                "请在前台「LLM 控制」中补全后重试"
            )

        settings = self._profile_to_settings(resolved)
        if resolved.protocol == "anthropic":
            return AnthropicProvider(settings)
        if resolved.protocol == "gemini":
            return GeminiProvider(settings)
        return OpenAIProvider(settings)

    def create_from_profile(self, profile: Optional[LLMProfile]) -> LLMService:
        # 不再退回 MockProvider：未配置时直接报错，让失败冒到调用方，
        # 避免「生成完成」的假象（mock 只保留给测试/离线评估脚本显式使用）
        if profile is None:
            raise LLMNotConfiguredError(
                "未找到任何 LLM 配置：请在前台「LLM 控制」中添加并激活一个模型档案"
            )

        resolved = self.control_service.resolve_profile(profile)
        return self.create_from_resolved_profile(resolved)

    def create_active_provider(self) -> LLMService:
        return self.create_from_resolved_profile(
            self.control_service.resolve_active_profile()
        )

    def create_from_profile_id(self, profile_id: str) -> LLMService:
        """根据档案 ID 创建 Provider；未找到时直接报错（不再退回 mock）。"""
        try:
            config = self.control_service.get_config()
            profile = next((p for p in config.profiles if p.id == profile_id), None)
        except Exception:
            profile = None
        if profile is None:
            raise LLMNotConfiguredError(f"未找到 LLM 档案 {profile_id}，无法创建独立 Provider")
        return self.create_from_profile(profile)

    def _profile_to_settings(self, profile: LLMProfile) -> Settings:
        if profile.protocol == "anthropic":
            normalized_base_url = normalize_anthropic_base_url(profile.base_url)
        elif profile.protocol == "gemini":
            normalized_base_url = normalize_gemini_base_url(profile.base_url)
        else:
            normalized_base_url = normalize_openai_base_url(profile.base_url)

        auth_mode = getattr(profile, "auth_mode", "api_key") or "api_key"
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
            use_oauth_bearer=(profile.protocol == "gemini" and auth_mode == "oauth"),
            loopback_only=(auth_mode == "local_gateway"),
        )


def _make_cache_key(profile: LLMProfile) -> str:
    """生成 Provider 缓存键，配置或完整密钥变化时自动重建 Provider。"""
    key_digest = hashlib.sha256((profile.api_key or "").encode("utf-8")).hexdigest()
    auth_mode = str(getattr(profile, "auth_mode", "api_key") or "api_key")
    oauth_provider = str(getattr(profile, "oauth_provider", "") or "")
    oauth_session_id = str(getattr(profile, "oauth_session_id", "") or "")
    headers_sig = json.dumps(profile.extra_headers or {}, sort_keys=True, ensure_ascii=False)
    query_sig = json.dumps(profile.extra_query or {}, sort_keys=True, ensure_ascii=False, default=str)
    body_sig = json.dumps(profile.extra_body or {}, sort_keys=True, ensure_ascii=False, default=str)
    key_parts = [
        profile.protocol or "",
        (profile.base_url or "").rstrip("/"),
        (profile.model or "").strip(),
        key_digest,
        auth_mode,
        oauth_provider,
        oauth_session_id,
        str(profile.temperature),
        str(profile.max_tokens),
        str(profile.timeout_seconds),
        str(profile.use_legacy_chat_completions),
        headers_sig,
        query_sig,
        body_sig,
    ]
    settings = Settings(timeout_seconds=profile.timeout_seconds)
    key_parts.extend(
        [
            str(settings.connect_timeout),
            str(settings.read_timeout),
            str(settings.write_timeout),
            str(settings.pool_timeout),
        ]
    )
    return "|".join(key_parts)


class DynamicLLMService(LLMService):
    """动态读取当前配置（支持 main / cheap / kg 三角色池缓存），并在配置不变时复用连接池。"""

    def __init__(self, factory: Optional[LLMProviderFactory] = None):
        self.factory = factory or LLMProviderFactory()
        self._cached_provider: Optional[LLMService] = None
        self._cached_key: Optional[str] = None
        self._role_cache: dict[str, tuple[str, LLMService]] = {}
        self._active_leases: dict[int, int] = {}
        self._retiring_providers: dict[int, LLMService] = {}
        self._closing_tasks: dict[int, asyncio.Task[None]] = {}
        self._retired_done_events: dict[int, asyncio.Event] = {}
        self._closed: bool = False
        self._cache_lock: Optional[asyncio.Lock] = None
        self._cache_lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_guard = threading.RLock()

    def _has_bound_loop_resources(self) -> bool:
        return bool(
            self._active_leases
            or self._retiring_providers
            or self._closing_tasks
            or self._retired_done_events
            or self._role_cache
            or self._cached_provider is not None
        )

    def _get_cache_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._loop_guard:
            if self._cache_lock_loop is None:
                self._cache_lock_loop = loop
                self._cache_lock = asyncio.Lock()
                return self._cache_lock
            if self._cache_lock_loop is loop:
                if self._cache_lock is None:
                    self._cache_lock = asyncio.Lock()
                return self._cache_lock
            if not self._cache_lock_loop.is_closed() or self._has_bound_loop_resources():
                raise RuntimeError(
                    "DynamicLLMService 已绑定到另一活跃或尚未完成资源清理的事件循环，拒绝跨事件循环访问"
                )
            self._cache_lock_loop = loop
            self._cache_lock = asyncio.Lock()
            return self._cache_lock

    def _is_cached(self, provider: LLMService) -> bool:
        if self._cached_provider is provider:
            return True
        return any(
            other_prov is provider for _, other_prov in self._role_cache.values()
        )

    async def _run_provider_close(self, pid: int, provider: LLMService) -> None:
        try:
            await self._close_provider_instance(provider)
        finally:
            self._closing_tasks.pop(pid, None)
            self._retiring_providers.pop(pid, None)
            done_ev = self._retired_done_events.pop(pid, None)
            if done_ev is not None:
                done_ev.set()

    def _retire_provider(self, provider: Optional[LLMService]) -> Optional[asyncio.Task[None]]:
        if provider is None:
            return None
        pid = id(provider)
        self._retiring_providers[pid] = provider
        if pid not in self._retired_done_events:
            self._retired_done_events[pid] = asyncio.Event()
        existing_task = self._closing_tasks.get(pid)
        if existing_task is not None and not existing_task.done():
            return existing_task
        if self._active_leases.get(pid, 0) > 0 or self._is_cached(provider):
            return None
        loop = asyncio.get_running_loop()
        task = loop.create_task(self._run_provider_close(pid, provider))
        self._closing_tasks[pid] = task
        return task

    def _release_lease_sync(self, provider: Optional[LLMService]) -> Optional[asyncio.Task[None]]:
        if provider is None:
            return None
        pid = id(provider)
        remaining = self._active_leases.get(pid, 0) - 1
        if remaining <= 0:
            self._active_leases.pop(pid, None)
        else:
            self._active_leases[pid] = remaining
        if remaining <= 0 and pid in self._retiring_providers and not self._is_cached(provider):
            return self._retire_provider(provider)
        return None

    async def _release_provider_lease(self, provider: Optional[LLMService]) -> None:
        if provider is None:
            return
        self._get_cache_lock()
        close_task = self._release_lease_sync(provider)
        if close_task is not None:
            await asyncio.shield(close_task)

    async def _resolve_provider(
        self,
        *,
        role: str = "main",
        _acquire_lease: bool = False,
    ) -> LLMService:
        evict_close_task: Optional[asyncio.Task[None]] = None
        async with self._get_cache_lock():
            if self._closed:
                raise RuntimeError("DynamicLLMService 已关闭，拒绝接纳新请求")
            effective_role: LLMRole = (
                role if role in ("main", "cheap", "kg") else "main"  # type: ignore[assignment]
            )
            ctrl = self.factory.control_service
            if hasattr(ctrl, "resolve_role_profile_async"):
                profile = await ctrl.resolve_role_profile_async(effective_role)
            elif hasattr(ctrl, "resolve_role_profile"):
                profile = ctrl.resolve_role_profile(effective_role)
            elif hasattr(ctrl, "resolve_active_profile_async"):
                profile = await ctrl.resolve_active_profile_async()
            else:
                profile = ctrl.resolve_active_profile()

            if self._closed:
                raise RuntimeError("DynamicLLMService 已关闭，拒绝接纳新请求")

            key = _make_cache_key(profile) if profile else "__mock__"

            cached_entry = self._role_cache.get(effective_role)
            if (
                cached_entry is None
                and effective_role == "main"
                and self._cached_provider is not None
                and self._cached_key is not None
            ):
                cached_entry = (self._cached_key, self._cached_provider)

            if cached_entry is not None:
                cached_key, cached_provider = cached_entry
                if (
                    cached_key == key
                    and cached_provider is not None
                    and id(cached_provider) not in self._retiring_providers
                ):
                    self._role_cache[effective_role] = (key, cached_provider)
                    if effective_role == "main":
                        self._cached_provider = cached_provider
                        self._cached_key = key
                    if _acquire_lease:
                        pid = id(cached_provider)
                        self._active_leases[pid] = self._active_leases.get(pid, 0) + 1
                    return cached_provider

                self._role_cache.pop(effective_role, None)
                if effective_role == "main":
                    self._cached_provider = None
                    self._cached_key = None

                if cached_provider is not None and not self._is_cached(cached_provider):
                    evict_close_task = self._retire_provider(cached_provider)

            # 若其他角色槽位已持有完全相同缓存键的活跃 Provider（回退主力时），直接共享连接池
            shared_provider = next(
                (
                    other_prov
                    for _, (other_key, other_prov) in self._role_cache.items()
                    if other_key == key
                    and other_prov is not None
                    and id(other_prov) not in self._retiring_providers
                ),
                None,
            )
            if shared_provider is not None:
                provider = shared_provider
            elif (
                hasattr(self.factory, "create_from_resolved_profile")
                and type(self.factory).create_from_profile is LLMProviderFactory.create_from_profile
            ):
                provider = self.factory.create_from_resolved_profile(profile)
            else:
                provider = self.factory.create_from_profile(profile)
            self._role_cache[effective_role] = (key, provider)
            if effective_role == "main":
                self._cached_provider = provider
                self._cached_key = key
            if _acquire_lease:
                pid = id(provider)
                self._active_leases[pid] = self._active_leases.get(pid, 0) + 1

            if shared_provider is None:
                logger.debug(
                    "Provider 缓存未命中，创建新实例: role=%s protocol=%s model=%s",
                    effective_role,
                    getattr(profile, "protocol", "?"),
                    getattr(profile, "model", "?"),
                )

        if evict_close_task is not None:
            try:
                await asyncio.shield(evict_close_task)
            except BaseException:
                if _acquire_lease:
                    await self._release_provider_lease(provider)
                raise

        return provider

    async def _close_provider_instance(self, old: Optional[LLMService]) -> None:
        if old is None:
            return
        try:
            if hasattr(old, "aclose"):
                await old.aclose()
            else:
                self._close_sync_clients(old)
                await self._close_async_clients(old)
        except Exception as exc:
            logger.debug("关闭旧 Provider 时出现可忽略异常: %s", exc)

    async def _close_cached_provider(self) -> None:
        """关闭所有角色缓存及兼容主缓存中的 Provider 连接资源（等待活跃租约释放且抗取消丢失）。"""
        self._get_cache_lock()
        self._closed = True

        seen_ids: set[int] = set()
        providers_to_retire: list[LLMService] = []

        for _, (_, prov) in list(self._role_cache.items()):
            if prov is not None and id(prov) not in seen_ids:
                seen_ids.add(id(prov))
                providers_to_retire.append(prov)

        if self._cached_provider is not None and id(self._cached_provider) not in seen_ids:
            seen_ids.add(id(self._cached_provider))
            providers_to_retire.append(self._cached_provider)

        for prov in list(self._retiring_providers.values()):
            if prov is not None and id(prov) not in seen_ids:
                seen_ids.add(id(prov))
                providers_to_retire.append(prov)

        self._role_cache.clear()
        self._cached_provider = None
        self._cached_key = None

        for prov in providers_to_retire:
            self._retire_provider(prov)

        wait_events = list(self._retired_done_events.values())
        if wait_events:
            await asyncio.gather(*(ev.wait() for ev in wait_events))

    @staticmethod
    def _close_sync_clients(provider: LLMService) -> None:
        for attr in ("_http_client_sync",):
            client = getattr(provider, attr, None)
            if client is not None and hasattr(client, "is_closed") and not client.is_closed:
                client.close()

    @staticmethod
    async def _close_async_clients(provider: LLMService) -> None:
        for attr in ("_http_client_async", "_http_client", "_stream_http_client"):
            client = getattr(provider, attr, None)
            if client is not None and hasattr(client, "aclose"):
                await client.aclose()

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
            role_hint=getattr(config, "role_hint", ""),
        )

    @staticmethod
    def _request_metadata(
        provider: LLMService,
        effective_config: GenerationConfig,
        *,
        llm_role: str = "main",
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
            "llm_role": llm_role,
        }
        if stream:
            metadata["stream"] = True
        return provider_label, generation_profile, model, metadata

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        trace = ensure_trace(operation="llm_generate", metadata={"entry": "DynamicLLMService.generate"})
        role = classify_llm_role(prompt, config, trace)
        provider = await self._resolve_provider(role=role, _acquire_lease=True)
        try:
            effective_config = self._merge_config(config, provider)
            request_span_id = trace.new_span_id("llm-request")
            recorder = get_trace_recorder()
            _, generation_profile, model, request_metadata = self._request_metadata(
                provider,
                effective_config,
                llm_role=role,
            )

            recorder.record_span(
                phase="llm_request",
                trace_context=trace,
                span_id=request_span_id,
                stage=trace.stage,
                stage_label=trace.stage_label,
                node_type="llm",
                model=model,
                generation_profile=generation_profile,
                prompt_hash=content_hash(prompt_to_hash_payload(prompt)),
                prompt_preview=prompt_preview(prompt),
                prompt_full=prompt_to_hash_payload(prompt),
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
                    stage=trace.stage,
                    stage_label=trace.stage_label,
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
                stage=trace.stage,
                stage_label=trace.stage_label,
                node_type="llm",
                model=model,
                generation_profile=generation_profile,
                response_hash=content_hash(content),
                response_preview=preview_text(content),
                response_full=content,
                token_input=getattr(usage, "input_tokens", None),
                token_output=getattr(usage, "output_tokens", None),
                latency_ms=int((time.perf_counter() - started) * 1000),
                metadata={**request_metadata, "content_length": len(content)},
            )
            return result
        finally:
            await self._release_provider_lease(provider)

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        trace = ensure_trace(
            operation="llm_stream_generate",
            metadata={"entry": "DynamicLLMService.stream_generate"},
        )
        role = classify_llm_role(prompt, config, trace)
        provider = await self._resolve_provider(role=role, _acquire_lease=True)
        stream_iter: Optional[AsyncIterator[str]] = None
        try:
            effective_config = self._merge_config(config, provider)
            request_span_id = trace.new_span_id("llm-stream-request")
            recorder = get_trace_recorder()
            _, generation_profile, model, request_metadata = self._request_metadata(
                provider,
                effective_config,
                llm_role=role,
                stream=True,
            )

            recorder.record_span(
                phase="llm_request",
                trace_context=trace,
                span_id=request_span_id,
                stage=trace.stage,
                stage_label=trace.stage_label,
                node_type="llm",
                model=model,
                generation_profile=generation_profile,
                prompt_hash=content_hash(prompt_to_hash_payload(prompt)),
                prompt_preview=prompt_preview(prompt),
                prompt_full=prompt_to_hash_payload(prompt),
                metadata=request_metadata,
            )
            started = time.perf_counter()
            response_parts: list[str] = []
            preview_parts: list[str] = []
            preview_chars = 0
            total_chars = 0
            try:
                stream_iter = provider.stream_generate(prompt, effective_config)
                async for chunk in stream_iter:
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
                    stage=trace.stage,
                    stage_label=trace.stage_label,
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
                    stage=trace.stage,
                    stage_label=trace.stage_label,
                    node_type="llm",
                    model=model,
                    generation_profile=generation_profile,
                    response_hash=content_hash(content_for_hash),
                    response_preview=preview_text("".join(preview_parts)),
                    response_full=content_for_hash,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    metadata={**request_metadata, "content_length": total_chars},
                )
        finally:
            try:
                if stream_iter is not None and hasattr(stream_iter, "aclose"):
                    await stream_iter.aclose()  # type: ignore[attr-defined]
            finally:
                await self._release_provider_lease(provider)

    async def aclose(self) -> None:
        """异步关闭缓存 Provider。"""
        await self._close_cached_provider()
