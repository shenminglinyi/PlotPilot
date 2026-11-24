"""
故事结构 API
"""

from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, StrictInt
from domain.structure.narrative_progress import NarrativeReviewConflict

from application.blueprint.services.story_structure_service import StoryStructureService
from application.blueprint.services.continuous_planning_service import ContinuousPlanningService
from interfaces.api.dependencies import get_chapter_renumber_coordinator
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.connection import get_database
from application.paths import get_db_path
import os


router = APIRouter(tags=["story-structure"])


def get_planning_service() -> ContinuousPlanningService:
    """获取 AI 规划服务实例"""
    db_path = get_db_path()
    story_node_repo = StoryNodeRepository(db_path)
    chapter_element_repo = ChapterElementRepository(db_path)

    # 使用统一的动态 LLM 服务（支持 OpenAI 兼容模型）
    from interfaces.api.dependencies import get_llm_service, get_bible_repository, get_novel_repository
    llm_service = get_llm_service()

    from application.world.services.bible_service import BibleService
    bible_service = BibleService(get_bible_repository())

    return ContinuousPlanningService(
        story_node_repo,
        chapter_element_repo,
        llm_service,
        bible_service,
        chapter_repository=SqliteChapterRepository(get_database()),
        novel_repository=get_novel_repository(),
    )


def get_service(
    planning_service: ContinuousPlanningService = Depends(get_planning_service)
) -> StoryStructureService:
    """获取故事结构服务实例

    注入 AI 规划服务，使 create_default_structure 方法能够使用 AI 动态生成结构。
    """
    db_path = get_db_path()
    repository = StoryNodeRepository(db_path)
    chapter_repo = SqliteChapterRepository(get_database())
    return StoryStructureService(
        repository,
        chapter_repository=chapter_repo,
        chapter_renumber_coordinator=get_chapter_renumber_coordinator(),
        planning_service=planning_service
    )


class CreateNodeRequest(BaseModel):
    """创建节点请求"""
    node_type: str  # "part" | "volume" | "act"
    number: int
    title: str
    parent_id: Optional[str] = None
    description: Optional[str] = None
    order_index: Optional[int] = None


class UpdateNodeRequest(BaseModel):
    """更新节点请求"""
    title: Optional[str] = None
    description: Optional[str] = None
    number: Optional[int] = None


class NarrativeEvidencePassage(BaseModel):
    chapter_number: StrictInt = Field(gt=0)
    quote: str = Field(min_length=1, max_length=4000)
    start: Optional[StrictInt] = Field(default=None, ge=0)


class NarrativeMilestoneReview(BaseModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool = True
    status: Literal['open', 'resolved'] = 'open'
    evidence_chapters: List[StrictInt] = Field(default_factory=list)
    evidence_passages: List[NarrativeEvidencePassage] = Field(default_factory=list)


class NarrativeEndingReview(BaseModel):
    reviewed_through_chapter: StrictInt
    core_conflict: NarrativeMilestoneReview
    character_outcomes: NarrativeMilestoneReview
    ending: NarrativeMilestoneReview
    required_promises: List[NarrativeMilestoneReview] = Field(default_factory=list)
    open_ending_notes: List[str] = Field(default_factory=list)


class NarrativeProgressReviewRequest(BaseModel):
    expected_plan_revision: Optional[str] = None
    chapter_budget: Optional[int] = Field(default=None, gt=0, strict=True)
    goal: Optional[str] = None
    milestones: Optional[List[NarrativeMilestoneReview]] = None
    ending_review: Optional[NarrativeEndingReview] = None


def get_narrative_progress_service():
    from application.blueprint.services.narrative_progress_service import NarrativeProgressService
    from interfaces.api.dependencies import get_novel_repository

    return NarrativeProgressService(StoryNodeRepository(get_db_path()),
                                    SqliteChapterRepository(get_database()), get_novel_repository())


@router.get('/novels/{novel_id}/structure/progress')
async def get_narrative_progress(novel_id: str, service=Depends(get_narrative_progress_service)):
    """Separate generated manuscript count from reviewed story completion."""
    try:
        return await service.get_report(novel_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.put('/novels/{novel_id}/structure/volumes/{volume_id}/progress')
async def review_narrative_progress(novel_id: str, volume_id: str,
                                   request: NarrativeProgressReviewRequest,
                                   service=Depends(get_narrative_progress_service)):
    try:
        payload = request.model_dump(exclude_unset=True)
        # Explicit null clears an old ending assessment after a replan.
        if payload.get('milestones', []) is None or payload.get('chapter_budget', 1) is None:
            raise ValueError('里程碑和章节预算不能为 null')
        return await service.save_review(novel_id, volume_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except NarrativeReviewConflict as error:
        raise HTTPException(status_code=409, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


class ReorderRequest(BaseModel):
    """重新排序请求"""
    node_ids: List[str]


@router.get("/novels/{novel_id}/structure")
async def get_structure_tree(
    novel_id: str,
    service: StoryStructureService = Depends(get_service)
):
    """获取小说的完整结构树"""
    try:
        return await service.get_tree(novel_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/novels/{novel_id}/structure/children")
async def get_children(
    novel_id: str,
    parent_id: Optional[str] = None,
    service: StoryStructureService = Depends(get_service)
):
    """获取子节点（用于渐进式加载）"""
    try:
        return {
            "parent_id": parent_id,
            "children": await service.get_children(novel_id, parent_id)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/novels/{novel_id}/structure/nodes")
async def create_node(
    novel_id: str,
    request: CreateNodeRequest,
    service: StoryStructureService = Depends(get_service)
):
    """创建节点"""
    try:
        node = await service.create_node(
            novel_id=novel_id,
            node_type=request.node_type,
            number=request.number,
            title=request.title,
            parent_id=request.parent_id,
            description=request.description,
            order_index=request.order_index
        )
        return {"success": True, "node": node}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/novels/{novel_id}/structure/nodes/{node_id}")
async def update_node(
    novel_id: str,
    node_id: str,
    request: UpdateNodeRequest,
    service: StoryStructureService = Depends(get_service)
):
    """更新节点"""
    try:
        node = await service.update_node(
            novel_id=novel_id,
            node_id=node_id,
            title=request.title,
            description=request.description,
            number=request.number
        )
        return {"success": True, "node": node}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/novels/{novel_id}/structure/nodes/{node_id}")
async def delete_node(
    novel_id: str,
    node_id: str,
    service: StoryStructureService = Depends(get_service)
):
    """删除节点"""
    try:
        success = await service.delete_node(node_id)
        if not success:
            raise HTTPException(status_code=404, detail="Node not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/novels/{novel_id}/structure/reorder")
async def reorder_nodes(
    novel_id: str,
    request: ReorderRequest,
    service: StoryStructureService = Depends(get_service)
):
    """重新排序节点"""
    try:
        nodes = await service.reorder_nodes(request.node_ids)
        return {"success": True, "nodes": nodes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/novels/{novel_id}/structure/update-ranges")
async def update_chapter_ranges(
    novel_id: str,
    service: StoryStructureService = Depends(get_service)
):
    """更新章节范围"""
    try:
        await service.update_chapter_ranges(novel_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateDefaultStructureRequest(BaseModel):
    """创建默认结构请求"""
    total_chapters: int = 100
    structure_preference: Optional[dict] = None  # 极速模式为 None，精密模式为 {"parts": 3, ...}


@router.post("/novels/{novel_id}/structure/create-default")
async def create_default_structure(
    novel_id: str,
    request: CreateDefaultStructureRequest,
    service: StoryStructureService = Depends(get_service)
):
    """创建默认结构（AI 动态规划）

    支持两种模式：
    - 极速模式：structure_preference=None，AI 自主决定最优结构
    - 精密模式：structure_preference={"parts": 3, "volumes_per_part": 3, "acts_per_volume": 3}
    """
    try:
        result = await service.create_default_structure(
            novel_id=novel_id,
            total_chapters=request.total_chapters,
            structure_preference=request.structure_preference
        )
        return {"success": True, "structure": result}
    except RuntimeError as e:
        # 配置错误（如 planning_service 未注入）
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
