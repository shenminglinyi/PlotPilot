"""三元组索引服务 - 提供三元组向量化和语义检索功能

Collection 命名约定：
- Collection 名称：novel_{novel_id}_triples
- Payload 结构：
  * triple_id: str - 三元组 ID
  * subject: str - 主体
  * predicate: str - 谓词
  * object: str - 客体
  * subject_type: str - 主体类型
  * object_type: str - 客体类型
  * description: str - 描述
  * chapter_number: int - 章节号
  * confidence: float - 置信度

使用场景：
- 语义检索相关三元组（"战斗相关的设定"）
- 触发词召回的向量补充
- 图谱子网的语义扩展
"""
import logging
from typing import List, Optional, Dict, Any

from domain.ai.services.embedding_service import EmbeddingService
from domain.ai.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class TripleIndexingService:
    """三元组索引服务

    负责将三元组向量化并写入向量存储，支持语义检索。
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService
    ):
        """初始化三元组索引服务

        Args:
            vector_store: 向量存储服务
            embedding_service: 嵌入服务
        """
        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self._embedding_dimension = embedding_service.get_dimension()

    def _get_collection_name(self, novel_id: str) -> str:
        """获取 collection 名称

        Args:
            novel_id: 小说 ID

        Returns:
            collection 名称，格式为 novel_{novel_id}_triples
        """
        return f"novel_{novel_id}_triples"

    def _triple_to_text(self, triple: Dict[str, Any]) -> str:
        """将三元组转换为可向量化的文本

        将三元组的各个部分组合成一个有意义的句子，
        以便进行语义检索。

        Args:
            triple: 三元组字典

        Returns:
            用于向量化的文本
        """
        parts = []

        # 主体 + 谓词 + 客体
        subject = triple.get("subject", "")
        predicate = triple.get("predicate", "")
        obj = triple.get("object", "")
        description = triple.get("description", "")

        # 基本关系句
        if subject and predicate and obj:
            parts.append(f"{subject}{predicate}{obj}")

        # 添加描述
        if description:
            parts.append(description)

        # 添加类型信息（有助于语义检索）
        subject_type = triple.get("subject_type", "")
        object_type = triple.get("object_type", "")

        if subject_type == "character":
            parts.append(f"角色:{subject}")
        elif subject_type == "location":
            parts.append(f"地点:{subject}")
        elif subject_type == "item":
            parts.append(f"道具:{subject}")

        if object_type == "character":
            parts.append(f"角色:{obj}")
        elif object_type == "location":
            parts.append(f"地点:{obj}")
        elif object_type == "item":
            parts.append(f"道具:{obj}")

        return " ".join(parts)

    async def ensure_collection(self, novel_id: str) -> None:
        """确保 collection 存在，如果不存在则创建

        Args:
            novel_id: 小说 ID

        Raises:
            RuntimeError: 如果创建 collection 失败
        """
        collection_name = self._get_collection_name(novel_id)

        existing_collections = await self._vector_store.list_collections()

        if collection_name not in existing_collections:
            await self._vector_store.create_collection(
                collection=collection_name,
                dimension=self._embedding_dimension
            )
            logger.info(f"Created collection: {collection_name}")

    async def index_triple(
        self,
        novel_id: str,
        triple: Dict[str, Any]
    ) -> None:
        """索引单个三元组

        Args:
            novel_id: 小说 ID
            triple: 三元组字典，包含 id, subject, predicate, object 等字段

        Raises:
            ValueError: 如果参数无效
            RuntimeError: 如果索引失败
        """
        triple_id = triple.get("id") or triple.get("triple_id")
        if not triple_id:
            raise ValueError("Triple must have an id")

        # 确保 collection 存在
        await self.ensure_collection(novel_id)

        # 转换为文本
        text = self._triple_to_text(triple)
        if not text.strip():
            logger.warning(f"Triple {triple_id} has no meaningful text, skipping")
            return

        # 生成 embedding
        vector = await self._embedding_service.embed(text)

        # 构造 payload
        payload = {
            "triple_id": triple_id,
            "subject": triple.get("subject", ""),
            "predicate": triple.get("predicate", ""),
            "object": triple.get("object", ""),
            "subject_type": triple.get("subject_type", ""),
            "object_type": triple.get("object_type", ""),
            "description": triple.get("description", ""),
            "chapter_number": triple.get("chapter_number") or triple.get("first_appearance"),
            "confidence": triple.get("confidence", 1.0),
            "text": text,
        }

        # 写入向量存储
        collection_name = self._get_collection_name(novel_id)
        await self._vector_store.insert(
            collection=collection_name,
            id=triple_id,
            vector=vector,
            payload=payload
        )

        logger.debug(f"Indexed triple: {triple_id}")

    async def index_triples_batch(
        self,
        novel_id: str,
        triples: List[Dict[str, Any]]
    ) -> int:
        """批量索引三元组

        Args:
            novel_id: 小说 ID
            triples: 三元组列表

        Returns:
            成功索引的数量
        """
        if not triples:
            return 0

        # 确保 collection 存在
        await self.ensure_collection(novel_id)

        # 批量生成 embeddings
        texts = [self._triple_to_text(t) for t in triples]
        valid_indices = [i for i, t in enumerate(texts) if t.strip()]

        if not valid_indices:
            logger.warning("No valid texts to index")
            return 0

        valid_texts = [texts[i] for i in valid_indices]
        valid_triples = [triples[i] for i in valid_indices]

        # 批量生成向量
        vectors = await self._embedding_service.embed_batch(valid_texts)

        # 批量写入
        collection_name = self._get_collection_name(novel_id)
        indexed = 0

        for triple, vector in zip(valid_triples, vectors):
            triple_id = triple.get("id") or triple.get("triple_id")
            if not triple_id:
                continue

            payload = {
                "triple_id": triple_id,
                "subject": triple.get("subject", ""),
                "predicate": triple.get("predicate", ""),
                "object": triple.get("object", ""),
                "subject_type": triple.get("subject_type", ""),
                "object_type": triple.get("object_type", ""),
                "description": triple.get("description", ""),
                "chapter_number": triple.get("chapter_number") or triple.get("first_appearance"),
                "confidence": triple.get("confidence", 1.0),
                "text": self._triple_to_text(triple),
            }

            await self._vector_store.insert(
                collection=collection_name,
                id=triple_id,
                vector=vector,
                payload=payload
            )
            indexed += 1

        logger.info(f"Indexed {indexed} triples for novel {novel_id}")
        return indexed

    async def search_triples(
        self,
        novel_id: str,
        query: str,
        limit: int = 10,
        min_score: float = 0.5,
        subject_type: Optional[str] = None,
        object_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """语义检索三元组

        Args:
            novel_id: 小说 ID
            query: 查询文本（如 "战斗技能"、"武器属性"）
            limit: 返回结果数量
            min_score: 最小相似度阈值
            subject_type: 过滤主体类型（可选）
            object_type: 过滤客体类型（可选）

        Returns:
            匹配的三元组列表，每个元素包含 score 和 payload
        """
        collection_name = self._get_collection_name(novel_id)

        existing = await self._vector_store.list_collections()
        if collection_name not in existing:
            await self.ensure_collection(novel_id)

        # 生成查询向量
        query_vector = await self._embedding_service.embed(query)

        # 执行向量搜索
        results = await self._vector_store.search(
            collection=collection_name,
            query_vector=query_vector,
            limit=limit * 2  # 多取一些，用于过滤
        )

        # 过滤结果
        filtered = []
        for hit in results:
            # 过滤相似度
            if hit.get("score", 0) < min_score:
                continue

            payload = hit.get("payload", {})

            # 过滤主体类型
            if subject_type and payload.get("subject_type") != subject_type:
                continue

            # 过滤客体类型
            if object_type and payload.get("object_type") != object_type:
                continue

            filtered.append(hit)

        return filtered[:limit]

    async def delete_triple(self, novel_id: str, triple_id: str) -> None:
        """从索引中删除三元组

        Args:
            novel_id: 小说 ID
            triple_id: 三元组 ID
        """
        collection_name = self._get_collection_name(novel_id)
        await self._vector_store.delete(
            collection=collection_name,
            id=triple_id
        )
        logger.debug(f"Deleted triple: {triple_id}")

    async def delete_collection(self, novel_id: str) -> None:
        """删除整个 collection

        Args:
            novel_id: 小说 ID
        """
        collection_name = self._get_collection_name(novel_id)
        await self._vector_store.delete_collection(collection_name)
        logger.info(f"Deleted collection: {collection_name}")

    def sync_search(
        self,
        novel_id: str,
        query: str,
        limit: int = 10,
        min_score: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """同步语义检索接口

        提供同步接口，用于非 async 上下文。

        Args:
            novel_id: 小说 ID
            query: 查询文本
            limit: 返回结果数量
            min_score: 最小相似度阈值

        Returns:
            匹配的三元组列表
        """
        import asyncio
        import concurrent.futures

        async def _search():
            return await self.search_triples(novel_id, query, limit, min_score)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_search())

        def _run_in_fresh_loop():
            return asyncio.run(_search())

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_in_fresh_loop).result()
