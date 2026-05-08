"""LLM 提供商基类"""
from abc import ABC
from domain.ai.services.llm_service import LLMService
from infrastructure.ai.config.settings import Settings


class BaseProvider(LLMService, ABC):
    """LLM 提供商基类

    所有 LLM 提供商的抽象基类，继承自 LLMService 接口。
    """

    def __init__(self, settings: Settings):
        """初始化提供商

        Args:
            settings: AI 配置设置
        """
        self.settings = settings
        self.last_stream_stop_reason: str = ""
