# infrastructure/ai/chromadb_vector_store.py
"""
基于 FAISS 的向量存储实现（纯本地，兼容 Windows）

⚠️ 重要：本模块采用懒加载（Lazy Import）策略。
  faiss / numpy 均不在模块顶层导入，而是在 __init__ 和各方法中
  按需导入。这样即使未安装 requirements-local.txt 的用户，
  import 本模块也不会崩溃。

使用 FAISS 进行向量检索，使用 JSON 文件管理元数据。
命名保持 ChromaDB 以兼容现有代码。
"""
from typing import List
import json
from pathlib import Path

from domain.ai.services.vector_store import VectorStore


class ChromaDBVectorStore(VectorStore):
    """基于 FAISS 的向量存储实现（纯本地，兼容 Windows）

    使用 FAISS 进行向量检索，使用 JSON 文件管理元数据。
    命名保持 ChromaDB 以兼容现有代码。

    所有重依赖（faiss, numpy）均采用懒加载策略。
    """

    def __init__(self, persist_directory: str = "./data/chromadb"):
        """
        初始化向量存储

        Args:
            persist_directory: 本地持久化目录
        """
        # 懒加载 faiss 和 numpy
        self._use_faiss = False
        try:
            import faiss
            import numpy as np  # noqa: F401
            self._use_faiss = True
        except ImportError as e:
            self._import_error = e

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collections = {}  # {collection_name: {"index": faiss.Index, "metadata": dict}}
        self._load_collections()

    def _load_collections(self):
        """加载所有已存在的集合"""
        if not self._use_faiss:
            return
        import faiss

        if not self.persist_directory.exists():
            return

        for collection_dir in self.persist_directory.iterdir():
            if collection_dir.is_dir():
                collection_name = collection_dir.name
                index_path = collection_dir / "index.faiss"
                metadata_path = collection_dir / "metadata.json"

                if index_path.exists() and metadata_path.exists():
                    index = faiss.read_index(str(index_path))
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    self.collections[collection_name] = {
                        "index": index,
                        "metadata": metadata
                    }

    def _save_collection(self, collection: str):
        """保存集合到磁盘"""
        if not self._use_faiss:
            return
        import faiss

        collection_dir = self.persist_directory / collection
        collection_dir.mkdir(parents=True, exist_ok=True)

        coll = self.collections[collection]
        index_path = collection_dir / "index.faiss"
        metadata_path = collection_dir / "metadata.json"

        faiss.write_index(coll["index"], str(index_path))
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(coll["metadata"], f, ensure_ascii=False, indent=2)

    async def insert(
        self,
        collection: str,
        id: str,
        vector: List[float],
        payload: dict
    ) -> None:
        """插入向量到集合中"""
        import numpy as np

        try:
            if collection not in self.collections:
                raise Exception(f"Collection {collection} does not exist")

            coll = self.collections[collection]
            vec_array = np.array([vector], dtype=np.float32)
            actual_dim = int(vec_array.shape[1])

            if coll["dimension"] != actual_dim:
                import logging
                logging.getLogger(__name__).warning(
                    "向量集合维度不匹配，自动重建 collection=%s old_dim=%d actual_dim=%d",
                    collection, coll["dimension"], actual_dim
                )
                await self.delete_collection(collection)
                await self.create_collection(collection, actual_dim)
                coll = self.collections[collection]

            # 如果 ID 已存在，先删除旧的
            if id in coll["metadata"]:
                await self.delete(collection, id)

            coll["metadata"][id] = {
                "vector": list(vector),
                "payload": payload
            }

            if self._use_faiss:
                coll["index"].add(vec_array)
                coll["metadata"][id]["idx"] = coll["index"].ntotal - 1
                self._save_collection(collection)
        except Exception as e:
            raise Exception(f"Failed to insert vector: {str(e)}")

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int
    ) -> List[dict]:
        """搜索相似向量"""
        import numpy as np

        try:
            if collection not in self.collections:
                raise Exception(f"Collection {collection} does not exist")

            coll = self.collections[collection]
            if not coll["metadata"]:
                return []

            query_array = np.array(query_vector, dtype=np.float32)
            output = []
            for vec_id, meta in coll["metadata"].items():
                vector = np.array(meta["vector"], dtype=np.float32)
                dist = float(np.sum((vector - query_array) ** 2))
                output.append(
                    {
                        "id": vec_id,
                        "score": 1.0 / (1.0 + dist),
                        "payload": meta["payload"],
                    }
                )

            output.sort(key=lambda item: item["score"], reverse=True)
            return output[:limit]
        except Exception as e:
            raise Exception(f"Failed to search vectors: {str(e)}")

    async def delete(
        self,
        collection: str,
        id: str
    ) -> None:
        """删除向量（标记删除，不重建索引）"""
        try:
            if collection not in self.collections:
                raise Exception(f"Collection {collection} does not exist")

            coll = self.collections[collection]
            if id in coll["metadata"]:
                del coll["metadata"][id]
                self._save_collection(collection)
        except Exception as e:
            raise Exception(f"Failed to delete vector: {str(e)}")

    async def create_collection(
        self,
        collection: str,
        dimension: int
    ) -> None:
        """创建集合（若已存在且维度匹配则跳过；维度不匹配时删除后重建）"""
        try:
            if collection in self.collections:
                existing_dim = self.collections[collection]["dimension"]
                if dimension == 0 or existing_dim == dimension:
                    return  # 未知维度(0)或维度匹配，跳过重建
                # 嵌入模型已更换，旧索引不兼容，重建
                import logging
                logging.getLogger(__name__).warning(
                    "向量集合维度不匹配，重建索引 collection=%s old_dim=%d new_dim=%d",
                    collection, existing_dim, dimension
                )
                await self.delete_collection(collection)

            self.collections[collection] = {
                "index": None,
                "dimension": dimension,
                "metadata": {}
            }
            if self._use_faiss:
                import faiss

                self.collections[collection]["index"] = faiss.IndexFlatL2(dimension)
                self._save_collection(collection)
        except Exception as e:
            raise Exception(f"Failed to create collection: {repr(e)}")

    async def delete_collection(
        self,
        collection: str
    ) -> None:
        """删除集合"""
        import shutil

        try:
            if collection in self.collections:
                del self.collections[collection]

            # 删除磁盘文件
            collection_dir = self.persist_directory / collection
            if collection_dir.exists():
                shutil.rmtree(collection_dir)
        except Exception as e:
            raise Exception(f"Failed to delete collection: {str(e)}")

    async def list_collections(self) -> List[str]:
        """列出所有集合"""
        try:
            return list(self.collections.keys())
        except Exception as e:
            raise Exception(f"Failed to list collections: {str(e)}")
