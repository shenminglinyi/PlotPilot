"""OpenAI LLM 提供商实现"""
import logging
import os
from typing import AsyncIterator

from openai import AsyncOpenAI

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider

logger = logging.getLogger(__name__)

# 从环境变量读取模型配置，默认使用 gpt-4o
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


class OpenAIProvider(BaseProvider):
    """OpenAI LLM 提供商实现
    
    使用 OpenAI API 实现 LLM 服务。
    """

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
            messages = [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user}
            ]
            
            response = await self.async_client.chat.completions.create(
                model=config.model or self.settings.default_model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
            
            if not response.choices or not response.choices[0].message.content:
                raise RuntimeError("API returned empty content")
                
            content = response.choices[0].message.content
            
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
            messages = [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user}
            ]
            
            stream = await self.async_client.chat.completions.create(
                model=config.model or self.settings.default_model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"[Stream] Failed: {e}")
            raise RuntimeError(f"Failed to stream text: {str(e)}") from e
