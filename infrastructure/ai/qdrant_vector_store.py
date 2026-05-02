"""Qdrant vector store adapter.

The heavy qdrant-client dependency is imported lazily so local users who rely
on the default FAISS-backed store can still import the application without it.
"""
from typing import List

from domain.ai.services.vector_store import VectorStore


class QdrantVectorStore(VectorStore):
    """VectorStore implementation backed by a remote Qdrant service."""

    def __init__(self, host: str = "localhost", port: int = 6333, api_key: str | None = None):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, PointStruct, VectorParams
        except ImportError as e:
            raise ImportError(
                "使用 Qdrant 向量库需要安装 qdrant-client：pip install qdrant-client"
            ) from e

        self.client = QdrantClient(host=host, port=port, api_key=api_key)
        self._Distance = Distance
        self._PointStruct = PointStruct
        self._VectorParams = VectorParams

    async def insert(
        self,
        collection: str,
        id: str,
        vector: List[float],
        payload: dict,
    ) -> None:
        self.client.upsert(
            collection_name=collection,
            points=[
                self._PointStruct(
                    id=id,
                    vector=vector,
                    payload=payload or {},
                )
            ],
        )

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int,
    ) -> List[dict]:
        results = self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
        )
        return [
            {
                "id": str(item.id),
                "score": float(item.score),
                "payload": item.payload or {},
            }
            for item in results
        ]

    async def delete(self, collection: str, id: str) -> None:
        self.client.delete(
            collection_name=collection,
            points_selector=[id],
        )

    async def create_collection(self, collection: str, dimension: int) -> None:
        existing = set(await self.list_collections())
        if collection in existing:
            return
        self.client.create_collection(
            collection_name=collection,
            vectors_config=self._VectorParams(
                size=dimension,
                distance=self._Distance.COSINE,
            ),
        )

    async def delete_collection(self, collection: str) -> None:
        self.client.delete_collection(collection_name=collection)

    async def list_collections(self) -> List[str]:
        result = self.client.get_collections()
        return [item.name for item in result.collections]
