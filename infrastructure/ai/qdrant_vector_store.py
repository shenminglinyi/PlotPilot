"""Qdrant 向量存储适配器。

该模块只在显式选择 Qdrant 时导入 qdrant-client，避免默认本地模式被远程
向量库依赖阻塞。接口与 domain.ai.services.vector_store.VectorStore 对齐。
"""
from __future__ import annotations

import uuid
from typing import List

from domain.ai.services.vector_store import VectorStore


class QdrantVectorStore(VectorStore):
    """Qdrant 向量存储实现。"""

    def __init__(self, host: str = "localhost", port: int = 6333, api_key: str | None = None):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, PointStruct, VectorParams
        except ImportError as exc:
            raise ImportError(
                "启用 Qdrant 向量存储需要安装 qdrant-client，请执行：pip install qdrant-client"
            ) from exc

        self._client = QdrantClient(host=host, port=port, api_key=api_key)
        self._Distance = Distance
        self._PointStruct = PointStruct
        self._VectorParams = VectorParams

    @staticmethod
    def _point_id(raw_id: str) -> str:
        """Qdrant point id 规范化：领域层继续使用可读 id，适配层转换为 UUID。"""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw_id))

    async def create_collection(self, collection: str, dimension: int) -> None:
        existing = {item.name for item in self._client.get_collections().collections}
        if collection in existing:
            return
        self._client.create_collection(
            collection_name=collection,
            vectors_config=self._VectorParams(size=dimension, distance=self._Distance.COSINE),
        )

    async def insert(self, collection: str, id: str, vector: List[float], payload: dict) -> None:
        stored_payload = dict(payload or {})
        stored_payload.setdefault("_vector_id", id)
        self._client.upsert(
            collection_name=collection,
            points=[self._PointStruct(id=self._point_id(id), vector=vector, payload=stored_payload)],
        )

    async def search(self, collection: str, query_vector: List[float], limit: int) -> List[dict]:
        rows = self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
        )
        return [
            {
                "id": str((row.payload or {}).get("_vector_id") or row.id),
                "score": float(row.score),
                "payload": row.payload or {},
            }
            for row in rows
        ]

    async def delete(self, collection: str, id: str) -> None:
        self._client.delete(collection_name=collection, points_selector=[self._point_id(id)])

    async def delete_collection(self, collection: str) -> None:
        self._client.delete_collection(collection_name=collection)

    async def list_collections(self) -> List[str]:
        return [item.name for item in self._client.get_collections().collections]
