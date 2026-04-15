# infrastructure/ai/qdrant_vector_store.py
from typing import List, Optional, Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from domain.ai.services.vector_store import VectorStore


class QdrantVectorStore(VectorStore):
    """Qdrant 向量存储实现"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        timeout: Optional[float] = None,
        https: Optional[bool] = None,
    ):
        """
        初始化 Qdrant 客户端

        Args:
            host: Qdrant 服务器地址（与 port 连用；若提供 url 则忽略）
            port: Qdrant REST 端口（默认 6333）
            api_key: Qdrant API 密钥（可选，云端常为必填）
            url: 完整服务 URL（可选，例如 https://xxx.cloud.qdrant.io:6333；优先于 host/port）
            timeout: 请求超时秒数（可选）
            https: 是否使用 HTTPS（仅 host/port 模式；为 None 时由客户端默认）
        """
        client_kwargs: dict[str, Any] = {}
        if url:
            client_kwargs["url"] = url.rstrip("/")
        else:
            client_kwargs["host"] = host
            client_kwargs["port"] = port
        if api_key:
            client_kwargs["api_key"] = api_key
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        if https is not None:
            client_kwargs["https"] = https
        self.client = QdrantClient(**client_kwargs)

    async def insert(
        self,
        collection: str,
        id: str,
        vector: List[float],
        payload: dict
    ) -> None:
        """插入向量到集合中"""
        try:
            point = PointStruct(
                id=id,
                vector=vector,
                payload=payload
            )
            self.client.upsert(
                collection_name=collection,
                points=[point]
            )
        except Exception as e:
            raise Exception(f"Failed to insert vector: {str(e)}")

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int
    ) -> List[dict]:
        """搜索相似向量"""
        try:
            results = self.client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=limit
            )

            return [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload
                }
                for result in results
            ]
        except Exception as e:
            raise Exception(f"Failed to search vectors: {str(e)}")

    async def delete(
        self,
        collection: str,
        id: str
    ) -> None:
        """删除向量"""
        try:
            self.client.delete(
                collection_name=collection,
                points_selector=[id]
            )
        except Exception as e:
            raise Exception(f"Failed to delete vector: {str(e)}")

    async def create_collection(
        self,
        collection: str,
        dimension: int
    ) -> None:
        """创建集合"""
        try:
            self.client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=Distance.COSINE
                )
            )
        except Exception as e:
            raise Exception(f"Failed to create collection: {str(e)}")

    async def delete_collection(
        self,
        collection: str
    ) -> None:
        """删除集合"""
        try:
            self.client.delete_collection(collection_name=collection)
        except Exception as e:
            raise Exception(f"Failed to delete collection: {str(e)}")

    async def list_collections(self) -> List[str]:
        """列出所有集合"""
        try:
            collections = self.client.get_collections()
            return [col.name for col in collections.collections]
        except Exception as e:
            raise Exception(f"Failed to list collections: {str(e)}")
