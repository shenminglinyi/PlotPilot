"""OpenAI LLM 提供商实现"""
import asyncio
import inspect
import logging
import openai
import httpx
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from application.ai.llm_retry_policy import LLM_MAX_TOTAL_ATTEMPTS, is_retryable_llm_error
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.http_timeout import build_httpx_timeout
from infrastructure.ai.loopback_transport import LoopbackOnlyAsyncTransport
from .base import BaseProvider
from .model_resolution import require_resolved_model_id

logger = logging.getLogger(__name__)


class _ResponsesTerminalError(RuntimeError):
    """Raised when an OpenAI Responses response or stream explicitly reports failure or incomplete termination."""


class _StreamCleanupError(RuntimeError):
    """Raised when closing an acquired OpenAI stream fails after normal stream completion."""


class OpenAIProvider(BaseProvider):
    """OpenAI LLM 提供商实现

    通过 use_legacy_chat_completions 显式选择协议：
    - False（默认）：走 Responses API，失败时自动降级到 Chat Completions
    - True：走 Chat Completions API
    """

    # 静态类级别缓存：记录哪些 base_url 不支持 Responses API，从而避免重复降级带来的延迟开销
    _fallback_to_chat_cache: set[str] = set()

    def __init__(self, settings: Settings):
        super().__init__(settings)

        if not settings.api_key:
            raise ValueError("API key is required for OpenAIProvider")

        self._use_legacy = settings.use_legacy_chat_completions

        client_kwargs = {
            "api_key": settings.api_key,
            "timeout": settings.timeout_seconds,
            "default_headers": settings.extra_headers or None,
            "default_query": settings.extra_query or None,
        }
        if settings.base_url:
            client_kwargs["base_url"] = settings.base_url

        self._http_client = httpx.AsyncClient(
            timeout=build_httpx_timeout(settings.http_timeout_settings),
            trust_env=False,
            follow_redirects=False if getattr(settings, "loopback_only", False) else False,
            transport=(
                LoopbackOnlyAsyncTransport()
                if getattr(settings, "loopback_only", False)
                else None
            ),
        )
        client_kwargs["http_client"] = self._http_client
        self.async_client = AsyncOpenAI(**client_kwargs)

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        try:
            base_url = self.settings.base_url or "https://api.openai.com/v1"
            use_responses = not self._use_legacy and base_url not in self.__class__._fallback_to_chat_cache

            if use_responses:
                try:
                    return await self._generate_via_responses(prompt, config)
                except _ResponsesTerminalError:
                    raise
                except (openai.NotFoundError, openai.BadRequestError) as e:
                    logger.info(f"Responses API unsupported for {base_url}, falling back to chat completions: {str(e)}")
                    self.__class__._fallback_to_chat_cache.add(base_url)
                except Exception as e:
                    # 某些网关在路径错误时可能不抛严格的 404 而是抛出其他错误，如果消息含有明确路径错误也尝试降级
                    if self._is_responses_fallback_error(e):
                        logger.info(f"Gateway returned error for Responses API ({base_url}), falling back: {str(e)}")
                        self.__class__._fallback_to_chat_cache.add(base_url)
                    else:
                        raise

            # 使用降级的 Chat Completions API
            return await self._generate_via_chat(prompt, config)
        except RuntimeError:
            raise
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to generate text: {str(e)}") from e

    async def _generate_via_chat(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        """Chat Completions API 非流式生成

        🔥 自适应容错策略：
        1. 如果指定了 json_schema response_format 但网关返回 400，自动降级到 json_object
        2. 如果内容为空，降级到流式聚合（部分网关非流式返回空但流式正常）
        3. 如果非流式与流式聚合都为空，按统一 LLM 重试预算进行有限重试
        """
        messages = self._build_messages(prompt)
        last_error: Exception | None = None

        for attempt in range(LLM_MAX_TOTAL_ATTEMPTS):
            request_kwargs = self._build_chat_request_kwargs(messages, config)
            try:
                try:
                    response = await self.async_client.chat.completions.create(**request_kwargs)
                except (openai.BadRequestError, openai.NotFoundError) as e:
                    # 🔥 json_schema 不支持时自动降级
                    if config.response_format and config.response_format.get("type") == "json_schema":
                        base_url = (self.settings.base_url or "").rstrip("/")
                        logger.info(
                            "json_schema 不支持，自动降级到 json_object: %s (错误: %s)",
                            base_url, str(e)[:100]
                        )
                        self.__class__._json_schema_unsupported_cache.add(base_url)
                        request_kwargs["response_format"] = {"type": "json_object"}
                        response = await self.async_client.chat.completions.create(**request_kwargs)
                    else:
                        raise

                content = self._extract_text_from_response(response)

                if not content:
                    logger.warning(
                        "OpenAI-compatible response returned empty non-stream content; "
                        "falling back to streaming aggregation (attempt=%d/%d)",
                        attempt + 1,
                        LLM_MAX_TOTAL_ATTEMPTS,
                    )
                    content, token_usage = await self._generate_via_stream(request_kwargs)
                    return GenerationResult(content=content, token_usage=token_usage)

                input_tokens = response.usage.prompt_tokens if response.usage else 0
                output_tokens = response.usage.completion_tokens if response.usage else 0
                return GenerationResult(
                    content=content,
                    token_usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
                )
            except Exception as exc:
                last_error = exc
                if attempt >= LLM_MAX_TOTAL_ATTEMPTS - 1 or not is_retryable_llm_error(exc):
                    raise
                delay = min(1.5 * (2 ** attempt), 8.0)
                logger.warning(
                    "OpenAI-compatible provider transient failure; retrying in %.1fs "
                    "(attempt=%d/%d): %s",
                    delay,
                    attempt + 1,
                    LLM_MAX_TOTAL_ATTEMPTS,
                    exc,
                )
                await asyncio.sleep(delay)

        if last_error is not None:
            raise last_error
        raise RuntimeError("API returned empty content")

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        try:
            base_url = self.settings.base_url or "https://api.openai.com/v1"
            use_responses = not self._use_legacy and base_url not in self.__class__._fallback_to_chat_cache

            if use_responses:
                yielded_any = False
                try:
                    # 尝试走 Responses 流式 API
                    request_kwargs = self._build_responses_request_kwargs(prompt, config, stream=True)
                    stream = await self.async_client.responses.create(**request_kwargs)
                    stream_exc: BaseException | None = None
                    try:
                        async for chunk in stream:
                            content = self._extract_text_from_responses_chunk(chunk)
                            if content:
                                yielded_any = True
                                yield content
                    except BaseException as exc:
                        stream_exc = exc
                        raise
                    finally:
                        await self._close_stream(stream, suppress_errors=stream_exc is not None)
                    return  # 正常完成则结束 generator
                except (_ResponsesTerminalError, _StreamCleanupError):
                    raise
                except (openai.NotFoundError, openai.BadRequestError) as e:
                    if yielded_any:
                        logger.error(f"[Responses Stream] Interrupted after partial output: {e}")
                        raise RuntimeError(
                            f"Responses stream interrupted after partial output: {e}"
                        ) from e
                    self.__class__._fallback_to_chat_cache.add(base_url)
                    logger.info(f"Stream: Responses API unsupported for {base_url}, falling back.")
                except Exception as e:
                    if yielded_any:
                        logger.error(f"[Responses Stream] Interrupted after partial output: {e}")
                        raise RuntimeError(
                            f"Responses stream interrupted after partial output: {e}"
                        ) from e
                    if self._is_responses_fallback_error(e):
                        self.__class__._fallback_to_chat_cache.add(base_url)
                        logger.info(f"Stream: Gateway returned error for Responses API ({base_url}), falling back.")
                    else:
                        logger.error(f"[Responses Stream] Failed: {e}")
                        raise

            # 降级：走原来的 Chat Completions 流式 API
            messages = self._build_messages(prompt)
            request_kwargs = self._build_chat_request_kwargs(messages, config, stream=True)
            stream = await self.async_client.chat.completions.create(**request_kwargs)
            chat_stream_exc: BaseException | None = None
            try:
                async for chunk in stream:
                    content = self._extract_text_from_stream_chunk(chunk)
                    if content:
                        yield content
            except BaseException as exc:
                chat_stream_exc = exc
                raise
            finally:
                await self._close_stream(stream, suppress_errors=chat_stream_exc is not None)
        except (RuntimeError, ValueError):
            raise
        except Exception as e:
            logger.error(f"[Stream] Failed: {e}")
            raise RuntimeError(f"Failed to stream text: {str(e)}") from e

    @staticmethod
    def _is_responses_fallback_error(exc: Exception) -> bool:
        msg = str(exc)
        return (
            "404" in msg
            or "Not Found" in msg
            or "400" in msg
            or "Account invalid" in msg
            or "INVALID_ARGUMENT" in msg
        )

    @staticmethod
    def _build_messages(prompt: Prompt) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user}
        ]

    # 🔥 记录已知不支持 json_schema 的 base_url（避免每次重试）
    _json_schema_unsupported_cache: set[str] = set()

    def _build_chat_request_kwargs(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="OpenAI 兼容",
        )
        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "extra_headers": self.settings.extra_headers or None,
            "extra_query": self.settings.extra_query or None,
            "extra_body": self.settings.extra_body or None,
            "timeout": self.settings.timeout_seconds,
        }

        # 🔥 response_format 自适应降级策略
        # 不同网关对 response_format 的支持程度不同：
        #   OpenAI 官方: json_schema ✅ | json_object ✅
        #   DeepSeek:     json_schema ❌ | json_object ✅
        #   Qwen/DashScope: json_schema ❌ | json_object ✅ (部分)
        #   豆包/Ark:     json_schema ❌ | json_object ✅ (部分)
        #   智谱/GLM:     json_schema ❌ | json_object ✅
        if config.response_format:
            fmt = config.response_format
            base_url = (self.settings.base_url or "").rstrip("/")

            if fmt.get("type") == "json_schema" and base_url in self.__class__._json_schema_unsupported_cache:
                # 已知不支持 json_schema，自动降级到 json_object
                logger.debug("json_schema 已知不支持，降级到 json_object: %s", base_url)
                kwargs["response_format"] = {"type": "json_object"}
            else:
                kwargs["response_format"] = fmt

        if stream:
            kwargs["stream"] = True
        return kwargs

    def _build_responses_request_kwargs(
        self,
        prompt: Prompt,
        config: GenerationConfig,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="OpenAI 兼容",
        )
        kwargs: dict[str, Any] = {
            "model": model_id,
            "instructions": prompt.system,
            "input": [{"role": "user", "content": prompt.user}],
            "temperature": config.temperature,
            "max_output_tokens": config.max_tokens,
            "extra_headers": dict(self.settings.extra_headers) if self.settings.extra_headers else None,
            "extra_query": dict(self.settings.extra_query) if self.settings.extra_query else None,
            "extra_body": dict(self.settings.extra_body) if self.settings.extra_body else None,
            "timeout": self.settings.timeout_seconds,
        }

        if stream:
            kwargs["stream"] = True
        return kwargs

    async def _generate_via_responses(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        """Responses API 非流式生成"""
        request_kwargs = self._build_responses_request_kwargs(prompt, config)
        response = await self.async_client.responses.create(**request_kwargs)
        self._raise_if_responses_terminal_error(response)

        content = self._extract_text_from_responses_response(response)
        if not content:
            status = self._response_field(response, "status", "unknown")
            incomplete = self._response_field(response, "incomplete_details", None)
            reason = self._response_field(incomplete, "reason", "") if incomplete else ""
            details = f"status={status}"
            if reason:
                details += f", incomplete_reason={reason}"
            raise RuntimeError(f"Responses API returned empty content ({details})")

        usage = self._response_field(response, "usage", None)
        input_tokens = self._usage_tokens(usage, "input_tokens", "prompt_tokens")
        output_tokens = self._usage_tokens(usage, "output_tokens", "completion_tokens")

        return GenerationResult(
            content=content,
            token_usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        )

    @staticmethod
    def _response_field(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @classmethod
    def _raise_if_responses_terminal_error(cls, payload: Any) -> None:
        """Explicitly fail on Responses terminal failure, incomplete, cancelled, or error events/objects."""
        if payload is None:
            return

        event_type = str(cls._response_field(payload, "type", "") or "").strip()
        resp_obj = cls._response_field(payload, "response", None)
        item_obj = cls._response_field(payload, "item", None)
        part_obj = cls._response_field(payload, "part", None)

        top_err = cls._response_field(payload, "error", None)
        resp_err = cls._response_field(resp_obj, "error", None) if resp_obj is not None else None
        item_err = cls._response_field(item_obj, "error", None) if item_obj is not None else None
        part_err = cls._response_field(part_obj, "error", None) if part_obj is not None else None

        bad_statuses = {"failed", "incomplete", "cancelled", "canceled"}
        resp_status = (
            str(cls._response_field(resp_obj, "status", "") or "").strip().lower()
            if resp_obj is not None
            else str(cls._response_field(payload, "status", "") or "").strip().lower()
        )
        item_status = (
            str(cls._response_field(item_obj, "status", "") or "").strip().lower()
            if item_obj is not None
            else ""
        )
        part_status = (
            str(cls._response_field(part_obj, "status", "") or "").strip().lower()
            if part_obj is not None
            else ""
        )

        terminal_error_events = {
            "response.failed",
            "response.incomplete",
            "response.cancelled",
            "response.canceled",
            "error",
        }
        effective_err = next(
            (e for e in (top_err, resp_err, item_err, part_err) if e is not None),
            None,
        )
        effective_bad_status = next(
            (s for s in (resp_status, item_status, part_status) if s in bad_statuses),
            "",
        )

        if (
            event_type not in terminal_error_events
            and effective_err is None
            and not effective_bad_status
        ):
            return

        status_source = resp_obj if resp_obj is not None else payload
        incomplete = (
            cls._response_field(status_source, "incomplete_details", None)
            or cls._response_field(payload, "incomplete_details", None)
        )
        reason = cls._response_field(incomplete, "reason", None) if incomplete is not None else None
        err_msg = (
            cls._response_field(effective_err, "message", None)
            if effective_err is not None
            else cls._response_field(payload, "message", None)
        )
        err_code = (
            cls._response_field(effective_err, "code", None)
            if effective_err is not None
            else cls._response_field(payload, "code", None)
        )

        details: list[str] = []
        if event_type:
            details.append(f"event={event_type}")
        if effective_bad_status:
            details.append(f"status={effective_bad_status}")
        if reason:
            details.append(f"incomplete_reason={reason}")
        if err_code:
            details.append(f"code={err_code}")
        if err_msg:
            details.append(f"message={err_msg}")
        elif effective_err is not None:
            details.append(f"error={effective_err}")

        summary = ", ".join(details) if details else "terminal error"
        raise _ResponsesTerminalError(f"OpenAI Responses generation failed ({summary})")

    @classmethod
    def _extract_text_from_responses_response(cls, response: Any) -> str:
        """Extract user-visible text from official SDK and compatible gateways.

        The Responses API uses ``output_text`` content parts.  Some compatible
        gateways still emit the older ``text`` spelling, so both are accepted.
        The SDK's aggregate ``response.output_text`` is preferred when present.
        """
        aggregate = cls._response_field(response, "output_text", "")
        if isinstance(aggregate, str) and aggregate.strip():
            return aggregate.strip()

        content_parts: list[str] = []
        for item in cls._response_field(response, "output", None) or []:
            if cls._response_field(item, "type", "") != "message":
                continue
            for part in cls._response_field(item, "content", None) or []:
                if cls._response_field(part, "type", "") not in {"output_text", "text"}:
                    continue
                piece = cls._response_field(part, "text", "")
                if isinstance(piece, str) and piece.strip():
                    content_parts.append(piece.strip())
        return "\n".join(content_parts).strip()

    @classmethod
    def _usage_tokens(cls, usage: Any, primary_name: str, legacy_name: str) -> int:
        if usage is None:
            return 0
        value = cls._response_field(usage, primary_name, None)
        if value is None:
            value = cls._response_field(usage, legacy_name, 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _extract_text_from_responses_chunk(cls, chunk: Any) -> str:
        """原生 Responses stream 解析封装（终态失败/截断事件显式抛错，绝不静默吞除）"""
        cls._raise_if_responses_terminal_error(chunk)
        try:
            event_type = cls._response_field(chunk, "type", "")
            if event_type == "response.output_text.delta":
                delta = cls._response_field(chunk, "delta", None)
                if isinstance(delta, str):
                    return delta
            elif event_type in ("response.content_part.added", "response.content_part.delta"):
                part = cls._response_field(chunk, "part", None)
                if part and cls._response_field(part, "type", "") in {"output_text", "text"}:
                    text_val = cls._response_field(part, "text", "")
                    return text_val if isinstance(text_val, str) else ""
                delta = cls._response_field(chunk, "delta", None)
                if isinstance(delta, str):
                    return delta
            elif event_type == "message.delta":
                delta = cls._response_field(chunk, "delta", None)
                if delta:
                    content = cls._response_field(delta, "content", None)
                    if isinstance(content, str):
                        return content
        except Exception:
            pass
        return ""

    @staticmethod
    def _normalize_chat_completion_content(content: Any) -> str:
        """兼容 message.content 为 str 或多段 content part 列表。

        🔥 自适应兼容多种网关的响应格式：
        1. 标准 OpenAI: content 是 str
        2. OpenAI 新协议: content 是 list[{type, text}]
        3. DeepSeek-R1: content 是 str，但 message.reasoning_content 单独存在
        4. 部分网关: content 是 list，包含 thinking/reasoning 类型 part
        5. 极端情况: content 是 None（空回复）
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    item_type = (item.get("type") or "").lower()
                    # 🔥 跳过推理/思考/拒绝类型的 content part
                    # DeepSeek-R1: reasoning_content 在 message 级别，不在 content part 中
                    # 但部分网关会把 thinking 放在 content part 里
                    if item_type in ("reasoning", "thinking", "refusal", "thought"):
                        continue
                    text_val = item.get("text")
                    if isinstance(text_val, str) and text_val.strip():
                        parts.append(text_val)
                else:
                    text_attr = getattr(item, "text", None)
                    if isinstance(text_attr, str) and text_attr.strip():
                        parts.append(text_attr)
            return "\n".join(parts).strip()

        return str(content).strip()

    @staticmethod
    def _extract_text_from_response(response: Any) -> str:
        resp_err = OpenAIProvider._response_field(response, "error", None)
        if resp_err is not None:
            err_msg = OpenAIProvider._response_field(resp_err, "message", None) or resp_err
            raise RuntimeError(f"OpenAI Chat Completions error: {err_msg}")
        if not getattr(response, "choices", None):
            return ""

        message = getattr(response.choices[0], "message", None)
        content = getattr(message, "content", None)
        result = OpenAIProvider._normalize_chat_completion_content(content)

        # 🔥 DeepSeek-R1 等模型：正文在 message.content，思考在 message.reasoning_content
        # reasoning_content 不需要返回给调用方（已经由 llm_output_sanitize 处理）
        # 但如果 content 为空且 reasoning_content 不为空，说明模型只输出了思考没有正文
        if not result.strip():
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning and isinstance(reasoning, str) and reasoning.strip():
                logger.debug("message.content 为空但有 reasoning_content，模型可能只输出了推理")

        return result

    @staticmethod
    async def _close_stream(stream: Any, *, suppress_errors: bool = False) -> None:
        close_fn = getattr(stream, "close", None)
        if not callable(close_fn):
            return
        try:
            result = close_fn()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            if suppress_errors:
                logger.warning("Failed to close OpenAI stream during unwind: %s", exc)
                return
            raise _StreamCleanupError(f"OpenAI stream cleanup failed: {exc}") from exc

    @staticmethod
    def _extract_text_from_stream_chunk(chunk: Any) -> str:
        chunk_err = OpenAIProvider._response_field(chunk, "error", None)
        if chunk_err is not None:
            err_msg = OpenAIProvider._response_field(chunk_err, "message", None) or chunk_err
            raise RuntimeError(f"OpenAI Chat Completions stream error: {err_msg}")
        if not getattr(chunk, "choices", None):
            # 容错：部分网关返回的流式 chunk 没有 choices 字段
            return ""

        choice = chunk.choices[0]
        delta = getattr(choice, "delta", None)
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return OpenAIProvider._normalize_chat_completion_content(content)
        return ""

    async def _generate_via_stream(self, request_kwargs: dict[str, Any]) -> tuple[str, TokenUsage]:
        stream = await self.async_client.chat.completions.create(
            **{**request_kwargs, "stream": True}
        )

        parts: list[str] = []
        input_tokens = 0
        output_tokens = 0
        stream_exc: BaseException | None = None

        try:
            async for chunk in stream:
                content = self._extract_text_from_stream_chunk(chunk)
                if content:
                    parts.append(content)

                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    output_tokens = getattr(usage, "completion_tokens", 0) or 0
        except BaseException as exc:
            stream_exc = exc
            raise
        finally:
            await self._close_stream(stream, suppress_errors=stream_exc is not None)

        content = "".join(parts).strip()
        if not content:
            raise RuntimeError("API returned empty content")

        return content, TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
