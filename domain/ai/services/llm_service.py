# domain/ai/services/llm_service.py
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage


class GenerationConfig:
    """生成配置"""
    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.__post_init__()

    def __post_init__(self):
        """验证配置参数"""
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("Temperature must be between 0.0 and 2.0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")


class GenerationResult:
    """生成结果"""
    def __init__(self, content: str, token_usage: TokenUsage):
        self.content = content
        self.token_usage = token_usage
        self.__post_init__()

    def __post_init__(self):
        """验证结果参数"""
        if not self.content or not self.content.strip():
            raise ValueError("Content cannot be empty")


class LLMService(ABC):
    """LLM 服务接口（领域服务）"""

    @abstractmethod
    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """生成内容"""
        pass

    @abstractmethod
    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容"""
        pass
