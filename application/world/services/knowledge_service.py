"""Knowledge application service"""
import logging
from typing import Optional, List, Dict, Any
from domain.knowledge.story_knowledge import StoryKnowledge
from domain.knowledge.chapter_summary import ChapterSummary
from domain.knowledge.knowledge_triple import KnowledgeTriple
from domain.knowledge.repositories.knowledge_repository import KnowledgeRepository
from domain.shared.exceptions import EntityNotFoundError

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识服务

    处理知识图谱的业务逻辑
    """

    def __init__(self, knowledge_repository: KnowledgeRepository):
        """初始化服务

        Args:
            knowledge_repository: 知识仓储
        """
        self.knowledge_repository = knowledge_repository

    def get_knowledge(self, novel_id: str) -> StoryKnowledge:
        """获取知识图谱

        Args:
            novel_id: 小说ID

        Returns:
            故事知识

        Raises:
            EntityNotFoundError: 如果知识图谱不存在
        """
        knowledge = self.knowledge_repository.get_by_novel_id(novel_id)
        if knowledge is None:
            # 返回空的知识图谱而不是抛出异常，保持向后兼容
            logger.info(f"Knowledge not found for {novel_id}, returning empty knowledge")
            return StoryKnowledge(novel_id=novel_id)
        return knowledge

    def update_knowledge(self, novel_id: str, data: Dict[str, Any]) -> StoryKnowledge:
        """更新知识图谱

        Args:
            novel_id: 小说ID
            data: 知识数据

        Returns:
            更新后的故事知识
        """
        # 构建章节摘要列表
        chapters = [
            ChapterSummary(
                chapter_id=ch["chapter_id"],
                summary=ch.get("summary", ""),
                key_events=ch.get("key_events", ""),
                open_threads=ch.get("open_threads", ""),
                consistency_note=ch.get("consistency_note", ""),
                beat_sections=ch.get("beat_sections", []),
                micro_beats=ch.get("micro_beats", []),
                sync_status=ch.get("sync_status", "draft")
            )
            for ch in data.get("chapters", [])
        ]

        # 构建知识三元组列表
        facts = [
            KnowledgeTriple(
                id=fact["id"],
                subject=fact.get("subject", ""),
                predicate=fact.get("predicate", ""),
                object=fact.get("object", ""),
                chapter_id=fact.get("chapter_id"),
                note=fact.get("note", ""),
                entity_type=fact.get("entity_type"),
                importance=fact.get("importance"),
                location_type=fact.get("location_type"),
                description=fact.get("description"),
                first_appearance=fact.get("first_appearance"),
                related_chapters=fact.get("related_chapters", []),
                tags=fact.get("tags", []),
                attributes=fact.get("attributes", {}),
                confidence=fact.get("confidence"),
                source_type=fact.get("source_type"),
                subject_entity_id=fact.get("subject_entity_id"),
                object_entity_id=fact.get("object_entity_id"),
            )
            for fact in data.get("facts", [])
        ]

        # 创建或更新知识图谱
        knowledge = StoryKnowledge(
            novel_id=novel_id,
            version=data.get("version", 1),
            premise_lock=data.get("premise_lock", ""),
            chapters=chapters,
            facts=facts
        )

        # 使用 save_all 方法保存
        logger.info(f"KnowledgeService: Calling save_all for {novel_id}, facts: {len(facts)}")
        self.knowledge_repository.save_all(novel_id, data)
        logger.info(f"Updated knowledge for {novel_id}: {len(chapters)} chapters, {len(facts)} facts")
        return knowledge

    def search_knowledge(self, novel_id: str, query: str, k: int = 6) -> Dict[str, Any]:
        """搜索知识图谱（向量优先策略）

        搜索优先级：
        1. 向量语义搜索（首选，语义理解强）
        2. 文本模糊匹配（降级方案，无网络依赖）

        如果向量索引不存在或为空，会自动从数据库加载三元组并建立索引。

        Args:
            novel_id: 小说ID
            query: 搜索查询
            k: 返回结果数量

        Returns:
            搜索结果 {"hits": [...]}
        """
        hits = []

        # ========== 方案1：向量语义搜索（优先）==========
        try:
            from interfaces.api.dependencies import get_triple_indexing_service
            indexing_service = get_triple_indexing_service()

            if indexing_service is not None:
                import concurrent.futures

                # 使用同步接口
                results = indexing_service.sync_search(
                    novel_id=novel_id,
                    query=query,
                    limit=k,
                    min_score=0.2,  # 降低阈值以获取更多候选
                )

                # 如果向量为空，尝试自动索引三元组
                if not results:
                    logger.info(f"Vector index empty for {novel_id}, attempting auto-index...")
                    try:
                        self._auto_index_triples(novel_id, indexing_service)
                        # 重新搜索
                        results = indexing_service.sync_search(
                            novel_id=novel_id,
                            query=query,
                            limit=k,
                            min_score=0.2,
                        )
                    except Exception as idx_err:
                        logger.warning(f"Auto-index failed: {idx_err}")

                if results:
                    seen_ids = set()
                    for r in results:
                        payload = r.get("payload", {})
                        triple_id = payload.get("triple_id", "")

                        # 去重
                        if triple_id and triple_id in seen_ids:
                            continue
                        seen_ids.add(triple_id)

                        subject = payload.get("subject", "")
                        predicate = payload.get("predicate", "")
                        obj = payload.get("object", "")
                        description = payload.get("description", "")

                        # 构建文本内容（用于 DTO 的 text 字段）
                        text_parts = [subject, predicate, obj] if predicate else [subject, obj]
                        if description:
                            text_parts.append(description)
                        display_text = "".join(text_parts)

                        hits.append({
                            "id": triple_id,
                            "text": display_text,
                            "meta": {
                                "subject": subject,
                                "predicate": predicate,
                                "object": obj,
                                "description": description,
                                "chapter_id": payload.get("chapter_number"),
                                "score": round(r.get("score", 0), 4),
                                "match_type": "semantic",
                            },
                        })

                    logger.info(f"Knowledge search (vector-first): {len(hits)} semantic hits for '{query}' in {novel_id}")

                    # 如果向量结果足够，直接返回
                    if len(hits) >= k:
                        return {"hits": hits[:k]}

                    # 否则继续用文本搜索补充
        except Exception as e:
            logger.warning(f"Vector search failed, fallback to text: {e}")

        # ========== 方案2：文本模糊匹配（补充/降级）==========
        try:
            knowledge = self.knowledge_repository.get_by_novel_id(novel_id)
            if knowledge and knowledge.facts:
                query_lower = query.lower()

                # 已有向量结果的 ID 集合，避免重复
                existing_ids = {h["id"] for h in hits}

                text_hits = []
                for fact in knowledge.facts:
                    # 跳过已有结果
                    if fact.id in existing_ids:
                        continue

                    subject = (fact.subject or "").lower()
                    predicate = (fact.predicate or "").lower()
                    obj = (fact.object or "").lower()
                    description = getattr(fact, 'description', "") or ""
                    description = description.lower() if description else ""

                    # 计算匹配分数
                    score = 0
                    if query_lower in subject:
                        score += 1.0
                    if query_lower in predicate:
                        score += 0.5
                    if query_lower in obj:
                        score += 1.0
                    if query_lower in description:
                        score += 0.3

                    if score > 0:
                        # 构建文本内容
                        text_parts = [fact.subject or "", fact.predicate or "", fact.object or ""]
                        display_text = "".join([p for p in text_parts if p])

                        text_hits.append({
                            "id": fact.id,
                            "text": display_text,
                            "meta": {
                                "subject": fact.subject,
                                "predicate": fact.predicate,
                                "object": fact.object,
                                "description": description,
                                "chapter_id": fact.chapter_id,
                                "entity_type": getattr(fact, 'entity_type', None),
                                "importance": getattr(fact, 'importance', None),
                                "score": score,
                                "match_type": "text",
                            },
                        })

                # 按分数排序
                text_hits.sort(key=lambda x: x.get("score", 0), reverse=True)

                # 合并结果：向量结果在前，文本结果在后
                needed = k - len(hits)
                if needed > 0 and text_hits:
                    hits.extend(text_hits[:needed])
                    logger.info(f"Knowledge search (text-supplement): +{min(needed, len(text_hits))} text hits")

        except Exception as e:
            logger.warning(f"Knowledge text search failed: {e}")

        logger.info(f"Knowledge search total: {len(hits)} hits for '{query}' in {novel_id}")
        return {"hits": hits[:k] if hits else []}

    def _auto_index_triples(self, novel_id: str, indexing_service) -> int:
        """自动从数据库加载三元组并建立向量索引

        当向量索引为空时调用，确保搜索能返回结果。

        Args:
            novel_id: 小说ID
            indexing_service: 三元组索引服务实例

        Returns:
            成功索引的三元组数量
        """
        import concurrent.futures
        import asyncio

        # 从数据库获取三元组（异步方法）
        try:
            from infrastructure.persistence.database.triple_repository import TripleRepository
            from application.paths import get_db_path

            db_path = get_db_path()
            triple_repo = TripleRepository(db_path)

            # 使用 asyncio.run 调用异步方法
            async def _load():
                return await triple_repo.get_by_novel(novel_id)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                triples = pool.submit(lambda: asyncio.run(_load())).result()

            if not triples:
                logger.info(f"No triples found in DB for {novel_id}")
                return 0

            # 转换为字典格式
            triple_dicts = []
            for t in triples:
                triple_dicts.append({
                    "id": t.id,
                    "subject": t.subject_id,
                    "predicate": t.predicate,
                    "object": t.object_id,
                    "subject_type": getattr(t, 'subject_type', None),
                    "object_type": getattr(t, 'object_type', None),
                    "description": getattr(t, 'description', "") or "",
                    "chapter_number": getattr(t, 'first_appearance', None),
                    "confidence": getattr(t, 'confidence', 1.0),
                })

            logger.info(f"Auto-indexing {len(triple_dicts)} triples for {novel_id}...")

            # 异步执行批量索引
            async def _index():
                return await indexing_service.index_triples_batch(novel_id, triple_dicts)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                indexed_count = pool.submit(lambda: asyncio.run(_index())).result()

            logger.info(f"Auto-indexed {indexed_count} triples for {novel_id}")
            return indexed_count

        except Exception as e:
            logger.error(f"Auto-index triples failed for {novel_id}: {e}", exc_info=True)
            return 0

    def upsert_chapter_summary(
        self,
        novel_id: str,
        chapter_id: int,
        summary: str = "",
        key_events: str = "",
        open_threads: str = "",
        consistency_note: str = "",
        beat_sections: List[str] = None,
        micro_beats: List[Dict[str, Any]] = None,
        sync_status: str = "draft"
    ) -> StoryKnowledge:
        """添加或更新章节摘要

        Args:
            novel_id: 小说ID
            chapter_id: 章节号
            summary: 章末总结
            key_events: 关键事件
            open_threads: 未解问题
            consistency_note: 一致性说明
            beat_sections: 节拍列表
            micro_beats: 微观节拍列表
            sync_status: 同步状态

        Returns:
            更新后的故事知识
        """
        knowledge = self.get_knowledge(novel_id)

        chapter = ChapterSummary(
            chapter_id=chapter_id,
            summary=summary,
            key_events=key_events,
            open_threads=open_threads,
            consistency_note=consistency_note,
            beat_sections=beat_sections or [],
            micro_beats=micro_beats or [],
            sync_status=sync_status
        )

        knowledge.add_or_update_chapter(chapter)
        self.knowledge_repository.save(knowledge)
        logger.info(f"Upserted chapter summary for {novel_id}, chapter {chapter_id}")
        return knowledge

    def upsert_fact(
        self,
        novel_id: str,
        fact_id: str,
        subject: str,
        predicate: str,
        object: str,
        chapter_id: Optional[int] = None,
        note: str = ""
    ) -> StoryKnowledge:
        """添加或更新知识三元组

        Args:
            novel_id: 小说ID
            fact_id: 三元组ID
            subject: 主语
            predicate: 谓词
            object: 宾语
            chapter_id: 章节号
            note: 备注

        Returns:
            更新后的故事知识
        """
        knowledge = self.get_knowledge(novel_id)

        fact = KnowledgeTriple(
            id=fact_id,
            subject=subject,
            predicate=predicate,
            object=object,
            chapter_id=chapter_id,
            note=note
        )

        knowledge.add_or_update_fact(fact)
        self.knowledge_repository.save(knowledge)
        logger.info(f"Upserted fact for {novel_id}: {fact_id}")
        return knowledge
