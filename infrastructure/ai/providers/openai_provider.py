"""OpenAI LLM 提供商实现"""
import logging
from typing import Any, AsyncIterator

import openai
from openai import AsyncOpenAI

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(BaseProvider):
    """OpenAI LLM 提供商实现
    
    能够自动探活并兼容最新的 Responses API (优先) 和传统的 Chat Completions API (降级)。
    """
    
    # 静态类级别缓存：记录哪些 base_url 不支持 Responses API，从而避免重复降级带来的延迟开销
    _fallback_to_chat_cache: set[str] = set()

    def __init__(self, settings: Settings):
        """初始化 OpenAI 提供商
        
        Args:
            settings: AI 配置设置
            
        Raises:
            ValueError: 如果 API key 未设置
        """
        super().__init__(settings)
        
        if not settings.api_key:
            raise ValueError("API key is required for OpenAIProvider")
            
        # 初始化 AsyncOpenAI 客户端
        client_kwargs = {
            "api_key": settings.api_key,
            "timeout": settings.timeout_seconds,
            "default_headers": settings.extra_headers or None,
            "default_query": settings.extra_query or None,
        }
        if settings.base_url:
            client_kwargs["base_url"] = settings.base_url
            
        self.async_client = AsyncOpenAI(**client_kwargs)

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """生成文本
        
        Args:
            prompt: 提示词
            config: 生成配置
            
        Returns:
            生成结果
            
        Raises:
            RuntimeError: 当 API 调用失败或返回空内容时
        """
        try:
            base_url = self.settings.base_url or "https://api.openai.com/v1"
            use_responses = base_url not in self.__class__._fallback_to_chat_cache
            
            if use_responses:
                try:
                    return await self._generate_via_responses(prompt, config)
                except openai.NotFoundError as e:
                    logger.info(f"Responses API unsupported for {base_url}, falling back to chat completions: {str(e)}")
                    self.__class__._fallback_to_chat_cache.add(base_url)
                except self.EmptyResponseError as e:
                    logger.warning(f"Responses API returned empty content for {base_url}, falling back to chat completions: {str(e)}")
                    self.__class__._fallback_to_chat_cache.add(base_url)
                except Exception as e:
                    # 某些网关在路径错误时可能不抛严格的 404 而是抛出其他错误，如果消息含有明确路径错误也尝试降级
                    if "404" in str(e) or "Not Found" in str(e):
                        logger.info(f"Gateway returned 404 for Responses API ({base_url}), falling back: {str(e)}")
                        self.__class__._fallback_to_chat_cache.add(base_url)
                    else:
                        raise
            
            # 使用降级的 Chat Completions API
            messages = self._build_messages(prompt)
            request_kwargs = self._build_chat_request_kwargs(messages, config)

            response = await self.async_client.chat.completions.create(**request_kwargs)
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
            token_usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            return GenerationResult(content=content, token_usage=token_usage)
            
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to generate text: {str(e)}") from e

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容
        
        Args:
            prompt: 提示词
            config: 生成配置
            
        Yields:
            生成的文本片段
            
        Raises:
            RuntimeError: 当流式生成失败时
        """
        try:
            base_url = self.settings.base_url or "https://api.openai.com/v1"
            use_responses = base_url not in self.__class__._fallback_to_chat_cache
            
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
                except openai.NotFoundError:
                    self.__class__._fallback_to_chat_cache.add(base_url)
                    logger.info(f"Stream: Responses API unsupported for {base_url}, falling back.")
                except self.EmptyResponseError:
                    self.__class__._fallback_to_chat_cache.add(base_url)
                    logger.warning(f"Stream: Responses API returned empty for {base_url}, falling back.")
                except Exception as e:
                    if "404" in str(e) or "Not Found" in str(e):
                        self.__class__._fallback_to_chat_cache.add(base_url)
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

    def _build_chat_request_kwargs(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": config.model or self.settings.default_model or DEFAULT_MODEL,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "extra_headers": self.settings.extra_headers or None,
            "extra_query": self.settings.extra_query or None,
            "extra_body": self.settings.extra_body or None,
            "timeout": self.settings.timeout_seconds,
        }
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
        kwargs: dict[str, Any] = {
            "model": config.model or self.settings.default_model or DEFAULT_MODEL,
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

    class EmptyResponseError(RuntimeError):
        """Responses API 返回空内容时的异常"""
        pass

    async def _generate_via_responses(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        """原生 Responses API 生成调用封装"""
        request_kwargs = self._build_responses_request_kwargs(prompt, config)
        response = await self.async_client.responses.create(**request_kwargs)
        
        output = getattr(response, "output", None)
        content = ""
        if output:
            for item in output:
                if getattr(item, "type", "") == "message":
                    for part in getattr(item, "content", []):
                        if getattr(part, "type", "") == "text":
                            content = str(getattr(part, "text", "")).strip()
                            break
        if not content:
            raise self.EmptyResponseError("Responses API returned empty content")
            
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
    def _extract_text_from_response(response: Any) -> str:
        if not getattr(response, "choices", None):
            return ""

        message = getattr(response.choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
        return ""

    @staticmethod
    def _extract_text_from_stream_chunk(chunk: Any) -> str:
        if not getattr(chunk, "choices", None):
            return ""

        delta = getattr(chunk.choices[0], "delta", None)
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            return content
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

		