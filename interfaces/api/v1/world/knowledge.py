"""Knowledge API routes"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from application.world.services.knowledge_service import KnowledgeService
from application.world.dtos.knowledge_dto import (
    StoryKnowledgeDTO,
    ChapterSummaryDTO,
    KnowledgeTripleDTO,
    KnowledgeSearchResponseDTO
)
from interfaces.api.dependencies import get_knowledge_service
from domain.shared.exceptions import EntityNotFoundError


router = APIRouter(prefix="/novels/{novel_id}/knowledge", tags=["knowledge"])


# Request Models
class UpdateKnowledgeRequest(BaseModel):
    """更新知识图谱请求"""
    version: int = Field(default=1, description="数据版本")
    premise_lock: str = Field(default="", description="梗概锁定")
    chapters: list[ChapterSummaryDTO] = Field(default_factory=list, description="章节摘要列表")
    facts: list[KnowledgeTripleDTO] = Field(default_factory=list, description="知识三元组列表")


# Routes
@router.get("", response_model=StoryKnowledgeDTO)
async def get_knowledge(
    novel_id: str,
    service: KnowledgeService = Depends(get_knowledge_service)
):
    """获取知识图谱

    Args:
        novel_id: 小说ID
        service: 知识服务

    Returns:
        故事知识 DTO
    """
    knowledge = service.get_knowledge(novel_id)

    return StoryKnowledgeDTO(
        version=knowledge.version,
        premise_lock=knowledge.premise_lock,
        chapters=[
            ChapterSummaryDTO(
                chapter_id=ch.chapter_id,
                summary=ch.summary,
                key_events=ch.key_events,
                open_threads=ch.open_threads,
                consistency_note=ch.consistency_note,
                beat_sections=ch.beat_sections,
                sync_status=ch.sync_status
            )
            for ch in knowledge.chapters
        ],
        facts=[
            KnowledgeTripleDTO(
                id=fact.id,
                subject=fact.subject,
                predicate=fact.predicate,
                object=fact.object,
                chapter_id=fact.chapter_id,
                note=fact.note,
                entity_type=fact.entity_type,
                importance=fact.importance,
                location_type=fact.location_type,
                description=fact.description,
                first_appearance=fact.first_appearance,
                related_chapters=fact.related_chapters,
                tags=fact.tags,
                attributes=fact.attributes,
                confidence=fact.confidence,
                source_type=fact.source_type,
                subject_entity_id=fact.subject_entity_id,
                object_entity_id=fact.object_entity_id,
                provenance=list(getattr(fact, "provenance", []) or []),
            )
            for fact in knowledge.facts
        ]
    )


@router.put("", response_model=StoryKnowledgeDTO)
async def update_knowledge(
    novel_id: str,
    request: UpdateKnowledgeRequest,
    service: KnowledgeService = Depends(get_knowledge_service)
):
    """更新知识图谱

    Args:
        novel_id: 小说ID
        request: 更新请求
        service: 知识服务

    Returns:
        更新后的故事知识 DTO
    """
    logger.debug("update_knowledge called for %s, facts: %d", novel_id, len(request.facts))

    try:
        data = {
            "version": request.version,
            "premise_lock": request.premise_lock,
            "chapters": [ch.model_dump() for ch in request.chapters],
            "facts": [fact.model_dump() for fact in request.facts]
        }

        knowledge = service.update_knowledge(novel_id, data)
    except Exception as e:
        logger.error("update_knowledge failed for %s: %s", novel_id, e)
        raise

    return StoryKnowledgeDTO(
        version=knowledge.version,
        premise_lock=knowledge.premise_lock,
        chapters=[
            ChapterSummaryDTO(
                chapter_id=ch.chapter_id,
                summary=ch.summary,
                key_events=ch.key_events,
                open_threads=ch.open_threads,
                consistency_note=ch.consistency_note,
                beat_sections=ch.beat_sections,
                sync_status=ch.sync_status
            )
            for ch in knowledge.chapters
        ],
        facts=[
            KnowledgeTripleDTO(
                id=fact.id,
                subject=fact.subject,
                predicate=fact.predicate,
                object=fact.object,
                chapter_id=fact.chapter_id,
                note=fact.note,
                entity_type=fact.entity_type,
                importance=fact.importance,
                location_type=fact.location_type,
                description=fact.description,
                first_appearance=fact.first_appearance,
                related_chapters=fact.related_chapters,
                tags=fact.tags,
                attributes=fact.attributes,
                confidence=fact.confidence,
                source_type=fact.source_type,
                subject_entity_id=fact.subject_entity_id,
                object_entity_id=fact.object_entity_id,
                provenance=list(getattr(fact, "provenance", []) or []),
            )
            for fact in knowledge.facts
        ]
    )


@router.get("/search", response_model=KnowledgeSearchResponseDTO)
async def search_knowledge(
    novel_id: str,
    q: str = Query(..., description="搜索查询"),
    k: int = Query(6, ge=1, le=50, description="返回结果数量"),
    service: KnowledgeService = Depends(get_knowledge_service)
):
    """搜索知识图谱

    Args:
        novel_id: 小说ID
        q: 搜索查询
        k: 返回结果数量
        service: 知识服务

    Returns:
        搜索结果
    """
    result = service.search_knowledge(novel_id, q, k)
    return KnowledgeSearchResponseDTO(**result)
