# infrastructure/ai/qdrant_vector_store.py
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from domain.ai.services.vector_store import VectorStore


class QdrantVectorStore(VectorStore):
    """Qdrant 向量存储实现"""

    def __init__(self, host: str = "localhost", port: int = 6333, api_key: str = None):
        """
        初始化 Qdrant 客户端

        Args:
            host: Qdrant 服务器地址
            port: Qdrant 服务器端口
            api_key: Qdrant API 密钥（可选）
        """
        self.client = QdrantClient(host=host, port=port, api_key=api_key)

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
            raise Exception(f"Failed to insert vector: [{type(e).__name__}] {str(e).splitlines()[0] if str(e) else repr(type(e))}")

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
            raise Exception(f"Failed to search vectors: {repr(e)}")

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
            raise Exception(f"Failed to delete vector: {repr(e)}")

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
            raise Exception(f"Failed to create collection: {repr(e)}")

    async def delete_collection(
        self,
        collection: str
    ) -> None:
        """删除集合"""
        try:
            self.client.delete_collection(collection_name=collection)
        except Exception as e:
            raise Exception(f"Failed to delete collection: {repr(e)}")

    async def list_collections(self) -> List[str]:
        """列出所有集合"""
        try:
            collections = self.client.get_collections()
            return [col.name for col in collections.collections]
        except Exception as e:
            raise Exception(f"Failed to list collections: {repr(e)}")
