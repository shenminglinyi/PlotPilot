"""OpenAI 嵌入服务实现"""
import os
from typing import List, Optional
from openai import AsyncOpenAI
from domain.ai.services.embedding_service import EmbeddingService


class OpenAIEmbeddingService(EmbeddingService):
    """OpenAI 嵌入服务实现

    使用 OpenAI 的 text-embedding-3-small 模型生成文本嵌入向量。
    支持从环境变量或显式参数初始化（用于数据库配置注入）。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """初始化 OpenAI 嵌入服务

        Args:
            api_key: API 密钥（不传则从环境变量读取）
            base_url: 自定义端点（不传则从环境变量读取）
            model: 模型名称（不传则从环境变量读取）

        Raises:
            ValueError: 如果 API Key 未设置
        """
        _api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not _api_key:
            raise ValueError("EMBEDDING_API_KEY or OPENAI_API_KEY environment variable is required")

        _base_url = base_url or os.getenv("EMBEDDING_BASE_URL") or None
        self.client = AsyncOpenAI(api_key=_api_key, base_url=_base_url)
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self._dimension: int = 0

    @classmethod
    def from_config(cls, config: dict) -> "OpenAIEmbeddingService":
        """从配置字典创建实例（供数据库配置使用）。

        Args:
            config: 包含 api_key, base_url, model 的字典

        Returns:
            OpenAIEmbeddingService 实例
        """
        return cls(
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url") or None,
            model=config.get("model"),
        )

    def get_dimension(self) -> int:
        return self._dimension

    async def _probe_dimension(self) -> None:
        if self._dimension > 0:
            return
        response = await self.client.embeddings.create(model=self.model, input="dim_probe")
        self._dimension = len(response.data[0].embedding)

    async def embed(self, text: str) -> List[float]:
        """生成单个文本的嵌入向量

        Args:
            text: 要嵌入的文本

        Returns:
            浮点数列表，表示文本的向量表示

        Raises:
            ValueError: 如果文本为空
            RuntimeError: 如果嵌入生成失败
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text
            )
            vec = response.data[0].embedding
            if self._dimension == 0:
                self._dimension = len(vec)
            return vec
        except Exception as e:
            raise RuntimeError(f"Failed to generate embedding: {str(e)}") from e

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成文本的嵌入向量

        Args:
            texts: 要嵌入的文本列表

        Returns:
            嵌入向量列表，每个元素对应一个输入文本的向量

        Raises:
            ValueError: 如果文本列表为空或包含空文本
            RuntimeError: 如果嵌入生成失败
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")

        if any(not text or not text.strip() for text in texts):
            raise ValueError("All texts must be non-empty")

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts
            )
            result = [item.embedding for item in response.data]
            if self._dimension == 0 and result:
                self._dimension = len(result[0])
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to generate embeddings: {str(e)}") from e
