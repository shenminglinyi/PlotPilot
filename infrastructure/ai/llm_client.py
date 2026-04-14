"""LLM Client Wrapper"""
import os
from typing import Optional, AsyncIterator
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.ark_provider import ArkProvider
from infrastructure.ai.providers.mock_provider import MockProvider
from infrastructure.ai.config.settings import Settings
from domain.ai.value_objects.prompt import Prompt
from domain.ai.services.llm_service import GenerationConfig


class LLMClient:
    """LLM Client Wrapper, auto-selects Anthropic, Ark, or Mock provider"""

    def __init__(self, provider=None):
        """Initialize LLM Client

        Args:
            provider: Optional LLM provider instance. If not provided, will auto-detect.
        """
        if provider:
            self.provider = provider
        else:
            # Auto-detect API key and select provider
            self.provider = self._auto_select_provider()

    def _auto_select_provider(self):
        """Auto-select provider based on environment variables

        Priority:
        1. ANTHROPIC_API_KEY -> AnthropicProvider
        2. ARK_API_KEY -> ArkProvider
        3. None -> MockProvider

        Returns:
            Selected provider instance
        """
        # Check for Anthropic first
        anthropic_key = self._get_anthropic_api_key()
        if anthropic_key:
            settings = Settings(
                api_key=anthropic_key,
                base_url=self._get_anthropic_base_url()
            )
            return AnthropicProvider(settings)

        # Check for Ark/DashScope
        ark_key = self._get_ark_api_key()
        if ark_key:
            settings = Settings(
                api_key=ark_key,
                base_url=self._get_ark_base_url()
            )
            return ArkProvider(settings)

        # Fallback to Mock
        return MockProvider()

    def _get_anthropic_api_key(self) -> Optional[str]:
        """Get Anthropic API key"""
        raw = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        if raw is None:
            return None
        key = raw.strip()
        return key or None

    def _get_anthropic_base_url(self) -> Optional[str]:
        """Get Anthropic base URL"""
        u = os.getenv("ANTHROPIC_BASE_URL")
        return u.strip() if u and u.strip() else None

    def _get_ark_api_key(self) -> Optional[str]:
        """Get Ark/DashScope API key"""
        raw = os.getenv("ARK_API_KEY")
        if raw is None:
            return None
        key = raw.strip()
        return key or None

    def _get_ark_base_url(self) -> Optional[str]:
        """Get Ark/DashScope base URL"""
        u = os.getenv("ARK_BASE_URL")
        return u.strip() if u and u.strip() else None

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text

        Args:
            prompt: Prompt string
            **kwargs: Other parameters (model, max_tokens, temperature, etc.)

        Returns:
            Generated text
        """
        # Create Prompt object
        prompt_obj = Prompt(
            system="You are a professional novel writing assistant.",
            user=prompt
        )

        # Create GenerationConfig object
        config = GenerationConfig(
            model=kwargs.get("model", os.getenv("ARK_MODEL", "qwen-turbo")),
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 1.0)
        )

        # Call provider
        result = await self.provider.generate(prompt_obj, config)
        return result.content

    async def stream_generate(
        self,
        prompt,          # Prompt object or str
        config=None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream generation, delegates to underlying provider"""
        # If string, convert to Prompt object
        if isinstance(prompt, str):
            prompt_obj = Prompt(
                system="You are a professional novel writing assistant.",
                user=prompt
            )
        else:
            prompt_obj = prompt

        # If no config provided, create default config
        if config is None:
            config = GenerationConfig(
                model=kwargs.get("model", os.getenv("ARK_MODEL", "qwen-turbo")),
                max_tokens=kwargs.get("max_tokens", 3000),
                temperature=kwargs.get("temperature", 0.85)
            )

        # Stream generation
        async for chunk in self.provider.stream_generate(prompt_obj, config):
            yield chunk
