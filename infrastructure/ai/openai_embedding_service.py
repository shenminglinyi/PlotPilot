"""OpenAI 嵌入服务实现"""
import os
from typing import List, Optional

import httpx
from openai import AsyncOpenAI
from domain.ai.services.embedding_service import EmbeddingService


class OpenAIEmbeddingService(EmbeddingService):
    """OpenAI 兼容的文本嵌入（具体模型 ID 由配置或环境变量提供，不在代码中写死）。"""

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
            model: 模型名称（不传则从环境变量 EMBEDDING_MODEL 读取）

        Raises:
            ValueError: 如果 API Key 或模型 ID 未设置
        """
        _api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not _api_key:
            raise ValueError("EMBEDDING_API_KEY or OPENAI_API_KEY environment variable is required")

        _base_url = base_url or os.getenv("EMBEDDING_BASE_URL") or None
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0), trust_env=False)
        self.client = AsyncOpenAI(
            api_key=_api_key,
            base_url=_base_url,
            http_client=self._http_client,
        )
        resolved = (model or os.getenv("EMBEDDING_MODEL") or "").strip()
        if not resolved:
            raise ValueError(
                "未配置嵌入模型 ID：请在数据库 embedding 设置中填写 model，或设置环境变量 EMBEDDING_MODEL。"
            )
        self.model = resolved
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
