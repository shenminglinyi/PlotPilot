"""Ark/DashScope LLM Provider Implementation"""
import json
import logging
import os
from typing import AsyncIterator
import httpx
from openai import OpenAI, AsyncOpenAI
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider

logger = logging.getLogger(__name__)

# Default model from environment variable
DEFAULT_MODEL = os.getenv("ARK_MODEL", "qwen-turbo")


class ArkProvider(BaseProvider):
    """Ark/DashScope LLM Provider Implementation

    Uses OpenAI-compatible API format for ByteDance Ark or Alibaba DashScope.
    """

    def __init__(self, settings: Settings):
        """Initialize Ark Provider

        Args:
            settings: AI configuration settings

        Raises:
            ValueError: If API key is not set
        """
        super().__init__(settings)

        if not settings.api_key:
            raise ValueError("API key is required for ArkProvider")

        # Get base URL from settings or environment
        base_url = settings.base_url or os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

        # OpenAI-compatible client
        # Create custom httpx clients to avoid proxy issues
        sync_http_client = httpx.Client(timeout=300.0)
        async_http_client = httpx.AsyncClient(timeout=300.0)

        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=base_url,
            max_retries=5,
            http_client=sync_http_client
        )
        self.async_client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=base_url,
            max_retries=5,
            http_client=async_http_client
        )
        self.base_url = base_url

        logger.info(f"ArkProvider initialized with base_url: {base_url}")

    def _convert_prompt(self, prompt: Prompt) -> list:
        """Convert Prompt to OpenAI message format

        Args:
            prompt: Domain prompt object

        Returns:
            List of messages in OpenAI format
        """
        messages = []
        if prompt.system:
            messages.append({"role": "system", "content": prompt.system})
        messages.append({"role": "user", "content": prompt.user})
        return messages

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """Generate text

        Args:
            prompt: Prompt
            config: Generation configuration

        Returns:
            Generation result

        Raises:
            RuntimeError: When API call fails or returns empty content
        """
        try:
            messages = self._convert_prompt(prompt)

            # Use DEFAULT_MODEL if config.model is not set or is a Claude model
            model = config.model
            if not model or "claude" in model.lower():
                model = DEFAULT_MODEL

            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

            # Defensive check
            if not response.choices or not response.choices[0].message:
                raise RuntimeError("API returned empty content")

            content = response.choices[0].message.content

            # Create token usage stats
            token_usage = TokenUsage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0
            )

            return GenerationResult(
                content=content,
                token_usage=token_usage
            )

        except Exception as e:
            logger.error(f"Ark API call failed: {e}")
            raise RuntimeError(f"Ark API call failed: {e}")

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """Stream generate text

        Args:
            prompt: Prompt
            config: Generation configuration

        Yields:
            Text chunks
        """
        try:
            messages = self._convert_prompt(prompt)

            # Use DEFAULT_MODEL if config.model is not set or is a Claude model
            model = config.model
            if not model or "claude" in model.lower():
                model = DEFAULT_MODEL

            stream = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content

        except Exception as e:
            logger.error(f"Ark stream generation failed: {e}")
            raise RuntimeError(f"Ark stream generation failed: {e}")

    def generate_sync(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """Synchronous text generation

        Args:
            prompt: Prompt
            config: Generation configuration

        Returns:
            Generation result
        """
        try:
            messages = self._convert_prompt(prompt)

            # Use DEFAULT_MODEL if config.model is not set or is a Claude model
            model = config.model
            if not model or "claude" in model.lower():
                model = DEFAULT_MODEL

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

            if not response.choices or not response.choices[0].message:
                raise RuntimeError("API returned empty content")

            content = response.choices[0].message.content

            token_usage = TokenUsage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0
            )

            return GenerationResult(
                content=content,
                token_usage=token_usage
            )

        except Exception as e:
            logger.error(f"Ark sync API call failed: {e}")
            raise RuntimeError(f"Ark sync API call failed: {e}")
