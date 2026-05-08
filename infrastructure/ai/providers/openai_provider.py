"""OpenAI LLM 提供商实现"""
import logging
import openai
import httpx
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider
from .model_resolution import require_resolved_model_id

logger = logging.getLogger(__name__)


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

        # 🔥 关键修复：分层超时配置
        # - connect_timeout: TCP 连接建立超时（30s，快速发现网络不可达）
        # - read_timeout: 等待服务端响应超时（120s，两个 SSE chunk 之间的间隔）
        # - write_timeout: 发送请求超时（60s）
        # - pool_timeout: 从连接池获取连接超时（30s）
        # 之前 httpx.Timeout(300) 是统一 300s，导致 deepseek API 卡住时整个进程挂起 1 小时
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.connect_timeout,
                read=settings.read_timeout,
                write=60.0,
                pool=30.0,
            ),
            trust_env=False,
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
                except (openai.NotFoundError, openai.BadRequestError, RuntimeError) as e:
                    logger.info(f"Responses API unsupported for {base_url}, falling back to chat completions: {str(e)}")
                    self.__class__._fallback_to_chat_cache.add(base_url)
                except Exception as e:
                    # 某些网关在路径错误时可能不抛严格的 404 而是抛出其他错误，如果消息含有明确路径错误也尝试降级
                    if "404" in str(e) or "Not Found" in str(e) or "400" in str(e) or "Account invalid" in str(e) or "INVALID_ARGUMENT" in str(e):
                        logger.info(f"Gateway returned error for Responses API ({base_url}), falling back: {str(e)}")
                        self.__class__._fallback_to_chat_cache.add(base_url)
                    else:
                        raise

            # 使用降级的 Chat Completions API
            return await self._generate_via_chat(prompt, config)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to generate text: {str(e)}") from e

    async def _generate_via_chat(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        """Chat Completions API 非流式生成

        🔥 自适应容错策略：
        1. 如果指定了 json_schema response_format 但网关返回 400，自动降级到 json_object
        2. 如果内容为空，降级到流式聚合（部分网关非流式返回空但流式正常）
        """
        messages = self._build_messages(prompt)
        request_kwargs = self._build_chat_request_kwargs(messages, config)

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
                # 重试：降级到 json_object
                request_kwargs["response_format"] = {"type": "json_object"}
                response = await self.async_client.chat.completions.create(**request_kwargs)
            else:
                raise

        content = self._extract_text_from_response(response)

        if not content:
            logger.warning(
                "OpenAI-compatible response returned empty non-stream content; "
                "falling back to streaming aggregation"
            )
            content, token_usage = await self._generate_via_stream(request_kwargs)
            return GenerationResult(content=content, token_usage=token_usage)

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        return GenerationResult(
            content=content,
            token_usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        try:
            base_url = self.settings.base_url or "https://api.openai.com/v1"
            use_responses = not self._use_legacy and base_url not in self.__class__._fallback_to_chat_cache

            if use_responses:
                try:
                    # 尝试走 Responses 流式 API
                    request_kwargs = self._build_responses_request_kwargs(prompt, config, stream=True)
                    stream = await self.async_client.responses.create(**request_kwargs)
                    async for chunk in stream:
                        content = self._extract_text_from_responses_chunk(chunk)
                        if content:
                            yield content
                    return  # 正常完成则结束 generator
                except (openai.NotFoundError, openai.BadRequestError):
                    self.__class__._fallback_to_chat_cache.add(base_url)
                    logger.info(f"Stream: Responses API unsupported for {base_url}, falling back.")
                except Exception as e:
                    if "404" in str(e) or "Not Found" in str(e) or "400" in str(e) or "Account invalid" in str(e) or "INVALID_ARGUMENT" in str(e):
                        self.__class__._fallback_to_chat_cache.add(base_url)
                        logger.info(f"Stream: Gateway returned error for Responses API ({base_url}), falling back.")
                    else:
                        logger.error(f"[Responses Stream] Failed: {e}")
                        raise

            # 降级：走原来的 Chat Completions 流式 API
            messages = self._build_messages(prompt)
            request_kwargs = self._build_chat_request_kwargs(messages, config, stream=True)
            stream = await self.async_client.chat.completions.create(**request_kwargs)
            async for chunk in stream:
                content = self._extract_text_from_stream_chunk(chunk)
                if content:
                    yield content
        except Exception as e:
            logger.error(f"[Stream] Failed: {e}")
            raise RuntimeError(f"Failed to stream text: {str(e)}") from e

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
        }
        if self.settings.extra_body:
             kwargs.update(self.settings.extra_body)

        if stream:
            kwargs["stream"] = True
        return kwargs

    async def _generate_via_responses(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        """Responses API 非流式生成"""
        request_kwargs = self._build_responses_request_kwargs(prompt, config)
        response = await self.async_client.responses.create(**request_kwargs)

        output = getattr(response, "output", None)
        content_parts: list[str] = []
        if output:
            for item in output:
                if getattr(item, "type", "") == "message":
                    for part in getattr(item, "content", []):
                        if getattr(part, "type", "") == "text":
                            piece = str(getattr(part, "text", "")).strip()
                            if piece:
                                content_parts.append(piece)
        content = "\n".join(content_parts).strip()
        if not content:
            raise RuntimeError("Responses API returned empty content")

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return GenerationResult(
            content=content,
            token_usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        )

    @staticmethod
    def _extract_text_from_responses_chunk(chunk: Any) -> str:
        """原生 Responses stream 解析封装"""
        try:
            event_type = getattr(chunk, "type", "")
            if event_type == "response.content_part.added":
                part = getattr(chunk, "part", None)
                if part and getattr(part, "type", "") == "text":
                    return getattr(part, "text", "")
            elif event_type == "message.delta":
                delta = getattr(chunk, "delta", None)
                if delta:
                     content = getattr(delta, "content", None)
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
    def _extract_text_from_stream_chunk(chunk: Any) -> str:
        if not getattr(chunk, "choices", None):
            # 🔥 容错：部分网关返回的流式 chunk 没有 choices 字段
            # 例如 DeepSeek-R1 的 reasoning_content 字段在顶层
            return ""

        choice = chunk.choices[0]
        delta = getattr(choice, "delta", None)
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return OpenAIProvider._normalize_chat_completion_content(content)
        return ""

    @staticmethod
    def _extract_text_from_stream_chunk(chunk: Any) -> str:
        if not getattr(chunk, "choices", None):
            return ""

        delta = getattr(chunk.choices[0], "delta", None)
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

        async for chunk in stream:
            content = self._extract_text_from_stream_chunk(chunk)
            if content:
                parts.append(content)

            usage = getattr(chunk, "usage", None)
            if usage is not None:
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0

        content = "".join(parts).strip()
        if not content:
            raise RuntimeError("API returned empty content")

        return content, TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
