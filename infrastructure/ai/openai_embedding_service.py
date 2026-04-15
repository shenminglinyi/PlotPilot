"""OpenAI 嵌入服务实现"""
import os
from typing import List
import httpx
from openai import AsyncOpenAI
from domain.ai.services.embedding_service import EmbeddingService


class OpenAIEmbeddingService(EmbeddingService):
    """OpenAI 嵌入服务实现

    使用 OpenAI 的 text-embedding-3-small 模型生成文本嵌入向量。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ):
        """初始化 OpenAI 嵌入服务

        Raises:
            ValueError: 如果 OPENAI_API_KEY 环境变量未设置
        """
        api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("EMBEDDING_API_KEY or OPENAI_API_KEY environment variable is required")

        base_url = base_url or os.getenv("EMBEDDING_API_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        client_kwargs = {
            "api_key": api_key,
            # 与 LLM Provider 一致：显式提供 http_client，规避 openai/httpx 的 proxies 参数兼容问题
            "http_client": httpx.AsyncClient(timeout=300.0),
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)
        self.model = model or os.getenv("EMBEDDING_API_MODEL", "text-embedding-3-small")
        dim_raw = str(dimension) if dimension is not None else os.getenv("EMBEDDING_API_DIMENSION")
        self._dimension = int(dim_raw) if dim_raw else 1536

    def get_dimension(self) -> int:
        """获取嵌入向量的维度

        Returns:
            1536 (text-embedding-3-small 模型的维度)
        """
        return self._dimension

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
            return response.data[0].embedding
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
            return [item.embedding for item in response.data]
        except Exception as e:
            raise RuntimeError(f"Failed to generate embeddings: {str(e)}") from e
