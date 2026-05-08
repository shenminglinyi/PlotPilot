"""LLM 提供商基类"""
import logging
from abc import ABC
from domain.ai.services.llm_service import LLMService
from infrastructure.ai.config.settings import Settings

logger = logging.getLogger(__name__)


class BaseProvider(LLMService, ABC):
    """LLM 提供商基类

    所有 LLM 提供商的抽象基类，继承自 LLMService 接口。
    提供 aclose() 清理接口用于关闭 HTTP 连接池。
    """

    def __init__(self, settings: Settings):
        """初始化提供商

        Args:
            settings: AI 配置设置
        """
        self.settings = settings

    async def aclose(self) -> None:
        """关闭 Provider 持有的 HTTP 连接池，释放系统资源（TCP 连接、TLS 上下文等）。

        子类可覆写此方法以关闭各自的 httpx client。
        默认实现自动检测并关闭常见的 client 属性。
        """
        closed_any = False
        # 关闭同步 httpx.Client
        for attr in ('_http_client_sync',):
            client = getattr(self, attr, None)
            if client is not None and hasattr(client, 'is_closed') and not client.is_closed:
                try:
                    client.close()
                    closed_any = True
                except Exception:
                    pass
        # 关闭异步 httpx.AsyncClient
        for attr in ('_http_client_async', '_http_client', '_stream_http_client'):
            client = getattr(self, attr, None)
            if client is not None and hasattr(client, 'aclose'):
                try:
                    await client.aclose()
                    closed_any = True
                except Exception:
                    pass
        if closed_any:
            logger.debug("Provider HTTP 连接池已关闭: %s", self.__class__.__name__)
