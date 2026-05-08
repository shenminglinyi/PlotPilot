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
import os
import uuid
import logging
from pathlib import Path

from domain.ai.services.vector_store import VectorStore
from domain.novel.value_objects.chapter_renumber_spec import ChapterRenumberSpec

_vector_renumber_log = logging.getLogger(__name__)


def _vector_payload_targets_novel(collection: str, novel_id: str, payload: dict) -> bool:
    """约定：novel_{id}_chunks / novel_{id}_triples 整库属于该书；其它 collection 用 payload.novel_id。"""
    if collection == f"novel_{novel_id}_chunks" or collection == f"novel_{novel_id}_triples":
        return True
    return payload.get("novel_id") == novel_id


def _vector_id_after_chapter_shift(
    collection: str,
    old_vector_id: str,
    payload: dict,
    novel_id: str,
    new_chapter_number: int,
) -> str:
    """与 ChapterIndexingService / IndexingService / TripleIndexingService 的 id 规则对齐。"""
    if collection == f"novel_{novel_id}_triples" or payload.get("triple_id"):
        return old_vector_id
    kind = payload.get("kind")
    if kind == "chapter_summary":
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{novel_id}_ch{new_chapter_number}_summary",
            )
        )
    if kind == "bible_snippet":
        raw = f"{novel_id}_ch{new_chapter_number}_bible"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))
    if collection == "chapters" or old_vector_id.startswith(f"{novel_id}_"):
        return f"{novel_id}_{new_chapter_number}"
    return old_vector_id


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
        try:
            import faiss
            import numpy as np
        except ImportError as e:
            raise ImportError(
                "检测到您正在尝试使用本地向量存储（ChromaDB/FAISS），"
                "但缺少必要的依赖包！\n\n"
                "请选择以下任一方式解决：\n"
                "  方式 A — 安装扩展依赖（~2GB）：\n"
                "    pip install -r requirements-local.txt\n\n"
                "  方式 B — 切换到 Qdrant 远程模式（推荐）：\n"
                "    设置环境变量 VECTOR_STORE_TYPE=qdrant\n\n"
                f"原始错误: {e}"
            ) from e

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collections = {}  # {collection_name: {"index": faiss.Index, "metadata": dict}}
        self._load_collections()

    def _load_collections(self):
        """加载所有已存在的集合"""
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
        import faiss

        try:
            if collection not in self.collections:
                raise Exception(f"Collection {collection} does not exist")

            coll = self.collections[collection]
            vec_array = np.array([vector], dtype=np.float32)
            actual_dim = int(vec_array.shape[1])

            # 用实际向量维度检测 FAISS 索引维度，不匹配则重建
            if coll["index"].d != actual_dim:
                import logging
                logging.getLogger(__name__).warning(
                    "FAISS索引维度不匹配，自动重建 collection=%s old_dim=%d actual_dim=%d",
                    collection, coll["index"].d, actual_dim
                )
                await self.delete_collection(collection)
                await self.create_collection(collection, actual_dim)
                coll = self.collections[collection]

            # 如果 ID 已存在，先删除旧的
            if id in coll["metadata"]:
                await self.delete(collection, id)

            # 添加到 FAISS 索引
            coll["index"].add(vec_array)
            idx = coll["index"].ntotal - 1

            # 保存元数据
            coll["metadata"][id] = {
                "idx": idx,
                "payload": payload
            }

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
            if coll["index"].ntotal == 0:
                return []

            query_array = np.array([query_vector], dtype=np.float32)
            distances, indices = coll["index"].search(query_array, min(limit, coll["index"].ntotal))

            # 构建 ID 到索引的反向映射
            idx_to_id = {v["idx"]: k for k, v in coll["metadata"].items()}

            # 转换为统一格式
            output = []
            for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                if idx == -1:  # FAISS 返回 -1 表示无效结果
                    continue

                vec_id = idx_to_id.get(int(idx))
                if vec_id:
                    # 将 L2 距离转换为相似度分数 (0-1)
                    score = 1.0 / (1.0 + float(dist))
                    output.append({
                        "id": vec_id,
                        "score": score,
                        "payload": coll["metadata"][vec_id]["payload"]
                    })

            return output
        except Exception as e:
            raise Exception(f"Failed to search vectors: {str(e)}")

    async def delete(
        self,
        collection: str,
        id: str
    ) -> None:
        """删除向量（标记删除 + 碎片整理）

        当累计删除数量超过阈值时自动触发 compact()，
        重建索引并回收已删除向量的空间，防止内存持续增长。
        """
        try:
            if collection not in self.collections:
                raise Exception(f"Collection {collection} does not exist")

            coll = self.collections[collection]
            if id in coll["metadata"]:
                del coll["metadata"][id]
                self._save_collection(collection)

                # 碎片整理：当 metadata 条目数 < 索引向量数的 50% 时触发重建
                self._maybe_compact(collection)
        except Exception as e:
            raise Exception(f"Failed to delete vector: {str(e)}")

    async def create_collection(
        self,
        collection: str,
        dimension: int
    ) -> None:
        """创建集合（若已存在且维度匹配则跳过；维度不匹配时删除后重建）"""
        import faiss

        try:
            if collection in self.collections:
                existing_dim = self.collections[collection]["index"].d
                if dimension == 0 or existing_dim == dimension:
                    return  # 未知维度(0)或维度匹配，跳过重建
                # 嵌入模型已更换，旧索引不兼容，重建
                import logging
                logging.getLogger(__name__).warning(
                    "向量集合维度不匹配，重建索引 collection=%s old_dim=%d new_dim=%d",
                    collection, existing_dim, dimension
                )
                await self.delete_collection(collection)

            # 创建 FAISS 索引（使用 L2 距离）
            index = faiss.IndexFlatL2(dimension)
            self.collections[collection] = {
                "index": index,
                "metadata": {}
            }
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

    def _maybe_compact(self, collection: str) -> None:
        """碎片整理：当 metadata 条目数远小于 FAISS 索引向量数时，重建索引。

        delete() 只从 metadata 移除记录，FAISS 索引体积只增不减。
        当碎片率超过 50%（索引中有一半以上的"僵尸"向量）时触发重建，
        回收内存并提高检索精度。
        """
        import faiss
        import numpy as np

        if collection not in self.collections:
            return

        coll = self.collections[collection]
        metadata_count = len(coll["metadata"])
        index_count = coll["index"].ntotal

        # 碎片率阈值：索引向量数 > metadata 条目数的 2 倍
        if index_count == 0 or metadata_count >= index_count * 0.5:
            return

        _vector_renumber_log.info(
            "FAISS 碎片整理开始: collection=%s index_vectors=%d metadata_entries=%d",
            collection, index_count, metadata_count,
        )

        try:
            # 收集所有存活向量的 ID 和索引
            alive_entries = [(vid, entry) for vid, entry in coll["metadata"].items()]
            if not alive_entries:
                return

            # 提取存活向量
            dimension = coll["index"].d
            vectors = []
            new_metadata = {}
            for new_idx, (vid, entry) in enumerate(alive_entries):
                old_idx = entry["idx"]
                vec = coll["index"].reconstruct(int(old_idx))
                vectors.append(vec)
                new_metadata[vid] = {"idx": new_idx, "payload": entry["payload"]}

            # 重建索引
            new_index = faiss.IndexFlatL2(dimension)
            if vectors:
                vec_array = np.array(vectors, dtype=np.float32)
                new_index.add(vec_array)

            coll["index"] = new_index
            coll["metadata"] = new_metadata
            self._save_collection(collection)

            _vector_renumber_log.info(
                "FAISS 碎片整理完成: collection=%s old=%d new=%d",
                collection, index_count, new_index.ntotal,
            )
        except Exception as e:
            _vector_renumber_log.warning("FAISS 碎片整理失败（不影响功能）: collection=%s err=%s", collection, e)

    async def compact_all(self) -> int:
        """对所有集合执行碎片整理。返回整理的集合数。"""
        count = 0
        for collection in list(self.collections.keys()):
            try:
                self._maybe_compact(collection)
                count += 1
            except Exception:
                pass
        return count

    async def list_collections(self) -> List[str]:
        """列出所有集合"""
        try:
            return list(self.collections.keys())
        except Exception as e:
            raise Exception(f"Failed to list collections: {str(e)}")

    def renumber_chapter_metadata_for_novel(
        self,
        spec: ChapterRenumberSpec,
        collection_names: List[str],
    ) -> int:
        """删章并重排章节号后，修正向量元数据中的 chapter_number（及需重建的 point id）。

        仅改写 metadata，不重算向量；与各 IndexingService 写入约定一致。
        """
        changed = 0
        for collection in collection_names:
            if collection not in self.collections:
                continue
            coll = self.collections[collection]
            meta = coll["metadata"]
            for old_id in list(meta.keys()):
                entry = meta.get(old_id)
                if not entry:
                    continue
                payload = entry.get("payload")
                if not isinstance(payload, dict):
                    continue
                if not _vector_payload_targets_novel(collection, spec.novel_id, payload):
                    continue
                raw_cn = payload.get("chapter_number")
                if raw_cn is None or isinstance(raw_cn, bool):
                    continue
                try:
                    cn_int = int(raw_cn)
                except (TypeError, ValueError):
                    continue
                new_cn = spec.shift_chapter_ref(cn_int)
                if new_cn == cn_int:
                    continue
                new_payload = dict(payload)
                new_payload["chapter_number"] = new_cn
                new_id = _vector_id_after_chapter_shift(
                    collection, old_id, new_payload, spec.novel_id, new_cn
                )
                entry["payload"] = new_payload
                if new_id == old_id:
                    meta[old_id] = entry
                    changed += 1
                    continue
                if new_id in meta:
                    _vector_renumber_log.warning(
                        "向量重编号 id 已存在，仅更新 payload，建议对该书重扫向量: "
                        "collection=%s old_id=%s new_id=%s",
                        collection,
                        old_id,
                        new_id,
                    )
                    meta[old_id] = entry
                    changed += 1
                    continue
                del meta[old_id]
                meta[new_id] = entry
                changed += 1
            self._save_collection(collection)
        return changed
