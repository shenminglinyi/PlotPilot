"""LLM 客户端包装器"""
import os
from typing import Optional, AsyncIterator
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.openai_provider import OpenAIProvider
from infrastructure.ai.providers.mock_provider import MockProvider
from infrastructure.ai.config.settings import Settings
from domain.ai.value_objects.prompt import Prompt
from domain.ai.services.llm_service import GenerationConfig


class LLMClient:
    """LLM 客户端包装器，根据 LLM_PROVIDER 自动选择提供者"""

    def __init__(self, provider=None):
        """初始化 LLM 客户端

        Args:
            provider: 可选的 LLM 提供者实例。如果未提供，将根据 LLM_PROVIDER 环境变量自动创建。
        """
        if provider:
            self.provider = provider
        else:
            self.provider = self._create_provider()

    def _create_provider(self):
        """根据环境变量创建合适的提供者"""
        provider_type = os.getenv("LLM_PROVIDER", "anthropic").lower()
        
        if provider_type == "openai":
            api_key = self._get_openai_api_key()
            if api_key:
                settings = Settings(
                    api_key=api_key,
                    base_url=self._get_openai_base_url()
                )
                return OpenAIProvider(settings)
        else:
            api_key = self._get_anthropic_api_key()
            if api_key:
                settings = Settings(
                    api_key=api_key,
                    base_url=self._get_anthropic_base_url()
                )
                return AnthropicProvider(settings)
        
        return MockProvider()

    def _get_openai_api_key(self) -> Optional[str]:
        """获取 OpenAI API key"""
        raw = os.getenv("OPENAI_API_KEY")
        if raw is None:
            return None
        key = raw.strip()
        return key or None

    def _get_openai_base_url(self) -> Optional[str]:
        """获取 OpenAI base URL"""
        u = os.getenv("OPENAI_BASE_URL")
        return u.strip() if u and u.strip() else None

    def _get_anthropic_api_key(self) -> Optional[str]:
        """获取 Anthropic API key"""
        raw = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        if raw is None:
            return None
        key = raw.strip()
        return key or None

    def _get_anthropic_base_url(self) -> Optional[str]:
        """获取 Anthropic base URL"""
        u = os.getenv("ANTHROPIC_BASE_URL")
        return u.strip() if u and u.strip() else None

    # 向后兼容方法
    def _get_api_key(self) -> Optional[str]:
        """获取 API key（向后兼容，使用 Anthropic）"""
        return self._get_anthropic_api_key()

    def _get_base_url(self) -> Optional[str]:
        """获取 base URL（向后兼容，使用 Anthropic）"""
        return self._get_anthropic_base_url()

    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本

        Args:
            prompt: 提示词字符串
            **kwargs: 其他参数（model, max_tokens, temperature等）

        Returns:
            生成的文本
        """
        # 创建 Prompt 对象
        prompt_obj = Prompt(
            system="你是一个专业的小说创作助手。",
            user=prompt
        )

        # 创建 GenerationConfig 对象（model 留空则由当前 Provider 按环境变量解析）
        config = GenerationConfig(
            model=kwargs.get("model"),
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 1.0)
        )

        # 调用 provider
        result = await self.provider.generate(prompt_obj, config)
        return result.content

    async def stream_generate(
        self,
        prompt,          # Prompt 对象或 str
        config=None,
        **kwargs
    ) -> AsyncIterator[str]:
        """流式生成，代理到底层 provider"""
        # 如果是字符串，转换为 Prompt 对象
        if isinstance(prompt, str):
            prompt_obj = Prompt(
                system="你是一个专业的小说创作助手。",
                user=prompt
            )
        else:
            prompt_obj = prompt

        # 如果没有提供 config，创建默认配置
        if config is None:
            config = GenerationConfig(
                max_tokens=kwargs.get("max_tokens", 3000),
                temperature=kwargs.get("temperature", 0.85)
            )

        # 流式生成
        async for chunk in self.provider.stream_generate(prompt_obj, config):
            yield chunk
