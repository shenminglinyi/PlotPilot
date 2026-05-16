"""生成工作流 API 端点"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.blueprint.services.continuous_planning_service import ContinuousPlanningService
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis
from application.engine.services.hosted_write_service import HostedWriteService
from application.paths import get_db_path
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.world.services.auto_bible_generator import AutoBibleGenerator
from application.world.services.auto_knowledge_generator import AutoKnowledgeGenerator
from domain.novel.entities.plot_arc import PlotArc
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.tension_level import TensionLevel
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from interfaces.api.dependencies import (
    get_auto_bible_generator,
    get_auto_knowledge_generator,
    get_auto_workflow,
    get_bible_service,
    get_chapter_service,
    get_hosted_write_service,
    get_novel_service,
    get_plot_arc_repository,
    get_setup_main_plot_suggestion_service,
    get_storyline_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["generation"])


def get_continuous_planning_service() -> ContinuousPlanningService:
    """获取持续规划服务"""
    db_path = get_db_path()
    story_node_repo = StoryNodeRepository(db_path)
    chapter_element_repo = ChapterElementRepository(db_path)

    from application.world.services.bible_service import BibleService
    from interfaces.api.dependencies import get_bible_repository, get_llm_service, get_chapter_repository

    bible_service = BibleService(get_bible_repository())
    llm_service = get_llm_service()
    chapter_repository = get_chapter_repository()

    return ContinuousPlanningService(
        story_node_repo=story_node_repo,
        chapter_element_repo=chapter_element_repo,
        llm_service=llm_service,
        bible_service=bible_service,
        chapter_repository=chapter_repository
    )


# Request/Response Models
class GenerateChapterRequest(BaseModel):
    """生成章节请求"""
    chapter_number: int = Field(..., gt=0, description="章节号（必须 > 0）")
    outline: str = Field(..., min_length=1, description="章节大纲")
    scene_director_result: Optional[dict] = Field(None, description="可选的场记分析结果")
    regeneration_guidance: Optional[str] = Field(
        None,
        max_length=2000,
        description="重新生成指导（告诉 AI 改进方向；仅用于重写已有章节时）",
    )


class StorylineMilestoneResponse(BaseModel):
    """故事线里程碑响应"""
    order: int
    title: str
    description: str = ""
    target_chapter_start: int
    target_chapter_end: int
    prerequisites: List[str] = []
    triggers: List[str] = []


class StorylineMergePoint(BaseModel):
    """故事线合并点（多线交汇的章节）"""
    chapter_number: int
    storyline_ids: List[str]
    merge_type: str = "convergence"  # convergence(汇聚) / divergence(分叉)
    description: str = ""


class StorylineResponse(BaseModel):
    """故事线响应（增强版，含里程碑）"""
    id: str
    storyline_type: str
    status: str
    estimated_chapter_start: int
    estimated_chapter_end: int
    name: str = ""
    description: str = ""
    milestones: List[StorylineMilestoneResponse] = []
    current_milestone_index: int = 0
    last_active_chapter: int = 0
    progress_summary: str = ""
    role: str = "main"
    parent_id: Optional[str] = None
    chapter_weight: float = 1.0


class StorylineGraphData(BaseModel):
    """Git Graph 视图所需的全量数据"""
    storylines: List[StorylineResponse]
    merge_points: List[StorylineMergePoint] = []
    total_chapters: int = 0


class CreateStorylineRequest(BaseModel):
    """创建故事线请求"""
    storyline_type: str = Field(..., description="故事线类型")
    estimated_chapter_start: int = Field(..., gt=0)
    estimated_chapter_end: int = Field(..., gt=0)
    name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="详细说明")
    role: Optional[str] = None               # 'main' | 'sub' | 'dark'
    parent_id: Optional[str] = None
    chapter_weight: float = 1.0


class MainPlotOptionItem(BaseModel):
    """向导推演得到的一条主线候选"""
    id: str
    type: str = ""
    title: str
    logline: str = ""
    core_conflict: str = ""
    starting_hook: str = ""


class SuggestMainPlotOptionsResponse(BaseModel):
    plot_options: List[MainPlotOptionItem]


def _storyline_to_response(storyline) -> StorylineResponse:
    milestones = []
    for ms in getattr(storyline, "milestones", []) or []:
        milestones.append(
            StorylineMilestoneResponse(
                order=ms.order,
                title=ms.title,
                description=ms.description,
                target_chapter_start=ms.target_chapter_start,
                target_chapter_end=ms.target_chapter_end,
                prerequisites=list(ms.prerequisites or []),
                triggers=list(ms.triggers or []),
            )
        )
    return StorylineResponse(
        id=storyline.id,
        storyline_type=storyline.storyline_type.value,
        status=storyline.status.value,
        estimated_chapter_start=storyline.estimated_chapter_start,
        estimated_chapter_end=storyline.estimated_chapter_end,
        name=getattr(storyline, "name", "") or "",
        description=getattr(storyline, "description", "") or "",
        milestones=milestones,
        current_milestone_index=getattr(storyline, "current_milestone_index", 0),
        last_active_chapter=getattr(storyline, "last_active_chapter", 0),
        progress_summary=getattr(storyline, "progress_summary", "") or "",
        role=storyline.role.value if hasattr(storyline, "role") and storyline.role else "main",
        parent_id=getattr(storyline, "parent_id", None),
        chapter_weight=getattr(storyline, "chapter_weight", 1.0),
    )


class PlotPointResponse(BaseModel):
    """情节点响应"""
    chapter_number: int
    tension: int
    description: str
    point_type: str = "rising"


class PlotArcResponse(BaseModel):
    """情节弧响应"""
    id: str
    novel_id: str
    key_points: List[PlotPointResponse]


class PlotPointRequest(BaseModel):
    """情节点请求"""
    chapter_number: int = Field(..., gt=0)
    tension: int = Field(..., ge=1, le=4)
    description: str
    point_type: str = Field(default="rising", description="情节点类型")


class CreatePlotArcRequest(BaseModel):
    """创建情节弧请求"""
    key_points: List[PlotPointRequest]


class HostedWriteStreamRequest(BaseModel):
    """托管连写（多章）请求"""
    from_chapter: int = Field(..., gt=0, description="起始章号")
    to_chapter: int = Field(..., gt=0, description="结束章号（含）")
    auto_save: bool = Field(True, description="每章生成后是否写入章节正文")
    auto_outline: bool = Field(
        True,
        description="是否先用模型生成本章要点大纲（否则用简短模板）",
    )


# Endpoints
@router.post(
    "/{novel_id}/generate-chapter-stream",
    status_code=status.HTTP_200_OK,
)
async def generate_chapter_stream(
    novel_id: str,
    request: GenerateChapterRequest,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow)
):
    """流式生成章节（SSE）

    每行一条 ``data: {json}``，事件类型：
    - ``phase``: ``planning`` | ``context`` | ``llm`` | ``post``
    - ``chunk``: 正文片段 ``text``
    - ``done``: 完整 ``content``、``consistency_report``、``token_count``
    - ``error``: ``message``
    """
    logger.info(f"API 请求: POST /{novel_id}/generate-chapter-stream (SSE)")
    logger.info(f"  章节号: {request.chapter_number}")
    logger.info(f"  大纲长度: {len(request.outline)} 字符")
    if request.regeneration_guidance:
        logger.info(f"  重写指导: {request.regeneration_guidance[:80]}")

    async def event_gen():
        # 转换 scene_director_result 为 SceneDirectorAnalysis（如果提供）
        scene_director = None
        if request.scene_director_result:
            scene_director = SceneDirectorAnalysis(**request.scene_director_result)

        async for event in workflow.generate_chapter_stream(
            novel_id=novel_id,
            chapter_number=request.chapter_number,
            outline=request.outline,
            scene_director=scene_director,
            regeneration_guidance=request.regeneration_guidance,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{novel_id}/hosted-write-stream",
    status_code=status.HTTP_200_OK,
)
async def hosted_write_stream(
    novel_id: str,
    request: HostedWriteStreamRequest,
    service: HostedWriteService = Depends(get_hosted_write_service),
):
    """托管多章连写（SSE）：自动大纲 → 每章流式正文 → 一致性 → 可选落库。

    额外事件：``session``、``chapter_start``、``outline``、``saved``、``session_done``；
    单章事件均带 ``chapter`` 字段。
    """
    logger.info(f"API 请求: POST /{novel_id}/hosted-write-stream (SSE)")
    logger.info(f"  章节范围: {request.from_chapter}-{request.to_chapter}")
    logger.info(f"  auto_save: {request.auto_save}, auto_outline: {request.auto_outline}")

    if request.to_chapter < request.from_chapter:
        logger.error(f"API 错误: to_chapter < from_chapter")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="to_chapter must be >= from_chapter",
        )

    async def event_gen():
        async for event in service.stream_hosted_write(
            novel_id=novel_id,
            from_chapter=request.from_chapter,
            to_chapter=request.to_chapter,
            auto_save=request.auto_save,
            auto_outline=request.auto_outline,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{novel_id}/setup/suggest-main-plot-options",
    response_model=SuggestMainPlotOptionsResponse,
    status_code=status.HTTP_200_OK,
)
async def suggest_main_plot_options(
    novel_id: str,
    novel_service=Depends(get_novel_service),
    setup_svc=Depends(get_setup_main_plot_suggestion_service),
):
    """向导 Step 4：根据 Bible 与小说元数据，由 LLM 推演 3 条主线候选。"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        raw = await setup_svc.suggest_options(novel_id)
        items = [MainPlotOptionItem(**opt) for opt in raw]
        return SuggestMainPlotOptionsResponse(plot_options=items)
    except Exception as e:
        logger.exception("suggest_main_plot_options failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to suggest main plot options: {str(e)}",
        )


@router.get(
    "/{novel_id}/storylines",
    response_model=List[StorylineResponse],
    status_code=status.HTTP_200_OK
)
def get_storylines(novel_id: str):
    """获取小说的所有故事线

    🔥 优化：从共享内存读取，不阻塞事件循环。
    """
    from application.engine.services.query_service import get_query_service

    try:
        query = get_query_service()
        storylines_raw = query.get_storylines(novel_id)

        # 转换为响应格式
        responses = []
        for sl in storylines_raw:
            responses.append(StorylineResponse(
                id=sl.get("id", ""),
                storyline_type=sl.get("storyline_type", "main"),
                status=sl.get("status", "active"),
                estimated_chapter_start=sl.get("estimated_chapter_start", 1),
                estimated_chapter_end=sl.get("estimated_chapter_end", 10),
                name=sl.get("name", ""),
                description=sl.get("description", ""),
                milestones=[
                    StorylineMilestoneResponse(
                        order=ms.get("order", 0),
                        title=ms.get("title", ""),
                        description=ms.get("description", ""),
                        target_chapter_start=ms.get("target_chapter_start", 1),
                        target_chapter_end=ms.get("target_chapter_end", 1),
                        prerequisites=ms.get("prerequisites", []),
                        triggers=ms.get("triggers", []),
                    )
                    for ms in sl.get("milestones", [])
                ],
                current_milestone_index=sl.get("current_milestone_index", 0),
                last_active_chapter=sl.get("last_active_chapter", 0),
                progress_summary=sl.get("progress_summary", ""),
            ))

        return responses
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get storylines: {str(e)}"
        )


@router.get(
    "/{novel_id}/storylines/graph-data",
    response_model=StorylineGraphData,
    status_code=status.HTTP_200_OK
)
def get_storyline_graph_data(novel_id: str):
    """获取 Git Graph 视图所需的全量数据（故事线 + 合并点）

    🔥 优化：从共享内存读取，不阻塞事件循环。
    """
    from application.engine.services.query_service import get_query_service

    try:
        query = get_query_service()
        storylines_raw = query.get_storylines(novel_id)

        # 转换为响应格式
        sl_responses = []
        for sl in storylines_raw:
            sl_responses.append(StorylineResponse(
                id=sl.get("id", ""),
                storyline_type=sl.get("storyline_type", "main"),
                status=sl.get("status", "active"),
                estimated_chapter_start=sl.get("estimated_chapter_start", 1),
                estimated_chapter_end=sl.get("estimated_chapter_end", 10),
                name=sl.get("name", ""),
                description=sl.get("description", ""),
                milestones=[],
                current_milestone_index=0,
                last_active_chapter=0,
                progress_summary="",
            ))

        # 自动计算合并点：多条故事线章节范围重叠的区间
        merge_points = _compute_merge_points(sl_responses)

        # 计算总章节数
        all_chapters = set()
        for sl in sl_responses:
            for c in range(sl.estimated_chapter_start, sl.estimated_chapter_end + 1):
                all_chapters.add(c)

        return StorylineGraphData(
            storylines=sl_responses,
            merge_points=merge_points,
            total_chapters=len(all_chapters),
        )
    except Exception as e:
        logger.exception("get_storyline_graph_data failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get graph data: {str(e)}"
        )


def _compute_merge_points(storylines: List[StorylineResponse]) -> List[StorylineMergePoint]:
    """自动计算故事线之间的合并点（章节重叠区域）

    算法：
      1. 收集所有 (chapter -> [storyline_ids]) 的映射
      2. 被 >=2 条线覆盖的章节即为合并点
      3. 将连续的合并章节约简为区间
    """
    if len(storylines) < 2:
        return []

    chapter_to_lines: Dict[int, List[str]] = {}
    for sl in storylines:
        for c in range(sl.estimated_chapter_start, sl.estimated_chapter_end + 1):
            if c not in chapter_to_lines:
                chapter_to_lines[c] = []
            chapter_to_lines[c].append(sl.id)

    # 找出被多条线覆盖的章节
    merge_chapters = sorted([c for c, ids in chapter_to_lines.items() if len(ids) >= 2])

    if not merge_chapters:
        return []

    # 将连续的合并章节约简为区间
    merge_points: List[StorylineMergePoint] = []
    start_ch = merge_chapters[0]
    prev_ch = merge_chapters[0]

    for ch in merge_chapters[1:]:
        if ch == prev_ch + 1:
            prev_ch = ch
        else:
            # 输出上一个区间
            ids = list(set(chapter_to_lines[start_ch]))
            merge_points.append(StorylineMergePoint(
                chapter_number=start_ch,
                storyline_ids=ids,
                merge_type="convergence",
                description=f"第{start_ch}-{prev_ch}章：{'、'.join(ids)} 汇合",
            ))
            start_ch = ch
            prev_ch = ch

    # 最后一个区间
    ids = list(set(chapter_to_lines[start_ch]))
    merge_points.append(StorylineMergePoint(
        chapter_number=start_ch,
        storyline_ids=ids,
        merge_type="convergence",
        description=f"第{start_ch}-{prev_ch}章：多线汇合推进",
    ))

    return merge_points


@router.post(
    "/{novel_id}/storylines",
    response_model=StorylineResponse,
    status_code=status.HTTP_201_CREATED
)
def create_storyline(
    novel_id: str,
    request: CreateStorylineRequest,
    manager: StorylineManager = Depends(get_storyline_manager)
):
    """创建新的故事线"""
    try:
        from domain.novel.value_objects.storyline_role import StorylineRole

        role = StorylineRole.MAIN
        if hasattr(request, 'role') and request.role:
            try:
                role = StorylineRole(request.role)
            except ValueError:
                role = StorylineRole.MAIN

        storyline = manager.create_storyline(
            novel_id=NovelId(novel_id),
            storyline_type=StorylineType(request.storyline_type),
            estimated_chapter_start=request.estimated_chapter_start,
            estimated_chapter_end=request.estimated_chapter_end,
            name=(request.name or "").strip(),
            description=(request.description or "").strip(),
            role=role,
            parent_id=getattr(request, 'parent_id', None),
            chapter_weight=getattr(request, 'chapter_weight', 1.0),
        )

        return _storyline_to_response(storyline)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create storyline: {str(e)}"
        )


class UpdateStorylineRequest(BaseModel):
    """更新故事线请求"""
    storyline_type: Optional[str] = None
    estimated_chapter_start: Optional[int] = Field(None, gt=0)
    estimated_chapter_end: Optional[int] = Field(None, gt=0)
    status: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


@router.put(
    "/{novel_id}/storylines/{storyline_id}",
    response_model=StorylineResponse,
    status_code=status.HTTP_200_OK
)
def update_storyline(
    novel_id: str,
    storyline_id: str,
    request: UpdateStorylineRequest,
    manager: StorylineManager = Depends(get_storyline_manager)
):
    """更新故事线"""
    try:
        storyline = manager.repository.get_by_id(storyline_id)
        if storyline is None or str(storyline.novel_id) != novel_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storyline not found")

        if request.storyline_type is not None:
            storyline.storyline_type = StorylineType(request.storyline_type)
        if request.estimated_chapter_start is not None:
            storyline.estimated_chapter_start = request.estimated_chapter_start
        if request.estimated_chapter_end is not None:
            storyline.estimated_chapter_end = request.estimated_chapter_end
        if request.status is not None:
            from domain.novel.value_objects.storyline_status import StorylineStatus
            storyline.status = StorylineStatus(request.status)
        if request.name is not None:
            storyline.name = request.name.strip()
        if request.description is not None:
            storyline.description = request.description.strip()

        manager.repository.save(storyline)

        return _storyline_to_response(storyline)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update storyline: {str(e)}"
        )


@router.delete(
    "/{novel_id}/storylines/{storyline_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_storyline(
    novel_id: str,
    storyline_id: str,
    manager: StorylineManager = Depends(get_storyline_manager)
):
    """删除故事线"""
    try:
        storyline = manager.repository.get_by_id(storyline_id)
        if storyline is None or str(storyline.novel_id) != novel_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storyline not found")
        manager.repository.delete(storyline_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete storyline: {str(e)}"
        )


@router.get(
    "/{novel_id}/plot-arc",
    response_model=PlotArcResponse,
    status_code=status.HTTP_200_OK
)
def get_plot_arc(novel_id: str):
    """获取小说的情节弧

    🔥 优化：从共享内存读取，不阻塞事件循环。
    """
    from application.engine.services.query_service import get_query_service

    try:
        query = get_query_service()
        plot_arc_raw = query.get_plot_arc(novel_id)

        if plot_arc_raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plot arc not found for novel {novel_id}"
            )

        # 转换关键点
        key_points = []
        for point in plot_arc_raw.get("key_points", []):
            key_points.append(PlotPointResponse(
                chapter_number=point.get("chapter_number", 1),
                tension=point.get("tension", 2),
                description=point.get("description", ""),
                point_type=point.get("point_type", "rising"),
            ))

        return PlotArcResponse(
            id=plot_arc_raw.get("id", f"{novel_id}-arc"),
            novel_id=novel_id,
            key_points=key_points,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plot arc: {str(e)}"
        )


@router.post(
    "/{novel_id}/plot-arc",
    response_model=PlotArcResponse,
    status_code=status.HTTP_200_OK
)
def create_or_update_plot_arc(
    novel_id: str,
    request: CreatePlotArcRequest,
    repository: PlotArcRepository = Depends(get_plot_arc_repository)
):
    """创建或更新情节弧"""
    try:
        # 尝试获取现有的情节弧
        plot_arc = repository.get_by_novel_id(NovelId(novel_id))

        if plot_arc is None:
            # 创建新的情节弧
            plot_arc = PlotArc(id=f"{novel_id}-arc", novel_id=NovelId(novel_id))

        # 清空现有的情节点并添加新的
        plot_arc.key_points = []
        for point_req in request.key_points:
            plot_arc.add_plot_point(PlotPoint(
                chapter_number=point_req.chapter_number,
                point_type=PlotPointType(point_req.point_type),
                description=point_req.description,
                tension=TensionLevel(point_req.tension)
            ))

        # 保存
        repository.save(plot_arc)

        return PlotArcResponse(
            id=plot_arc.id,
            novel_id=novel_id,
            key_points=[
                PlotPointResponse(
                    chapter_number=point.chapter_number,
                    tension=point.tension.value,
                    description=point.description,
                    point_type=point.point_type.value if hasattr(point.point_type, 'value') else str(point.point_type)
                )
                for point in plot_arc.key_points
            ]
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create/update plot arc: {str(e)}"
        )


# ============================================================================
# 新增：大纲规划、章节审稿、续写大纲
# ============================================================================

class PlanRequest(BaseModel):
    """大纲规划请求"""
    mode: str = Field("initial", description="模式：initial=首次生成，revise=再规划")
    dry_run: bool = Field(False, description="预演模式（不调用 LLM）")


class PlanResponse(BaseModel):
    """大纲规划响应"""
    success: bool
    message: str
    bible_updated: bool = False
    outline_updated: bool = False
    chapters_planned: int = 0
    structure_created: bool = False
    nodes_created: int = 0


class ReviewRequest(BaseModel):
    """章节审稿请求"""
    chapter_number: int = Field(..., gt=0, description="章节号")


class ReviewResponse(BaseModel):
    """章节审稿响应"""
    chapter_number: int
    suggestions: List[str]
    score: int = Field(..., ge=0, le=100, description="评分 0-100")


class ExtendOutlineRequest(BaseModel):
    """续写大纲请求"""
    from_chapter: int = Field(..., gt=0, description="从第几章开始续写")
    count: int = Field(5, gt=0, le=20, description="续写章节数量")


class ExtendOutlineResponse(BaseModel):
    """续写大纲响应"""
    success: bool
    chapters_added: int
    outlines: List[str]


@router.post(
    "/{novel_id}/plan",
    response_model=PlanResponse,
    status_code=status.HTTP_200_OK
)
async def plan_novel(
    novel_id: str,
    request: PlanRequest,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow),
    bible_service = Depends(get_bible_service),
    novel_service = Depends(get_novel_service),
    chapter_service = Depends(get_chapter_service),
    continuous_planning_service: ContinuousPlanningService = Depends(get_continuous_planning_service)
):
    """大纲规划：根据世界观、文约、初始地图、初始角色，AI 自主生成部-卷-幕结构

    - mode=initial: 首次生成（适用于新书）
    - mode=revise: 再规划（基于已有进度重新规划）
    - dry_run=true: 预演模式，不调用 LLM

    AI 会根据 Bible 中的世界观、角色、地点等信息，自主决定部/卷/幕的数量和结构
    """
    try:
        logger.info(f"[PlanNovel] Starting plan for novel {novel_id}")

        if request.dry_run:
            return PlanResponse(
                success=True,
                message="预演模式：跳过 LLM 调用",
                bible_updated=False,
                outline_updated=False,
                chapters_planned=0,
                structure_created=False,
                nodes_created=0
            )

        # 获取小说信息
        logger.info(f"[PlanNovel] Getting novel info")
        novel = novel_service.get_novel(novel_id)
        if not novel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Novel {novel_id} not found"
            )
        logger.info(f"[PlanNovel] Novel found: {novel.title}")

        # 生成 + 落库与全托管共用 ContinuousPlanningService.apply_macro_plan_from_llm_result
        logger.info(f"[PlanNovel] Calling generate_macro_plan (AI autonomous planning)")
        macro_plan = await continuous_planning_service.generate_macro_plan(
            novel_id=novel_id,
            target_chapters=novel.target_chapters,
            structure_preference=None,
        )
        logger.info(f"[PlanNovel] Macro plan generated, persisting (shared path with autopilot)")

        confirm_result = await continuous_planning_service.apply_macro_plan_from_llm_result(
            macro_plan,
            novel_id=novel_id,
            target_chapters=novel.target_chapters,
            minimal_fallback_on_empty=True,
        )

        logger.info(
            f"Persisted macro structure: nodes={confirm_result['created_nodes']}, "
            f"minimal_fallback={confirm_result.get('used_minimal_fallback')}"
        )

        if confirm_result.get("used_minimal_fallback"):
            msg = (
                f"LLM 未返回有效结构，已写入占位骨架；共 {confirm_result['created_nodes']} 个结构节点"
            )
        else:
            msg = confirm_result.get("message") or (
                f"成功创建 {confirm_result['created_nodes']} 个结构节点"
            )

        return PlanResponse(
            success=True,
            message=msg,
            bible_updated=False,
            outline_updated=False,
            chapters_planned=0,
            structure_created=True,
            nodes_created=confirm_result["created_nodes"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Plan failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan failed: {str(e)}"
        )


@router.post(
    "/{novel_id}/chapters/{chapter_number}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_200_OK
)
async def review_chapter(
    novel_id: str,
    chapter_number: int,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow),
    chapter_service = Depends(get_chapter_service)
):
    """章节审稿：AI 审稿并返回修改建议"""
    try:
        # 读取章节内容
        chapter = chapter_service.get_chapter_by_novel_and_number(novel_id, chapter_number)
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chapter {chapter_number} not found"
            )

        # 使用一致性检查作为审稿
        # TODO: 这里可以调用专门的审稿 LLM prompt
        suggestions = [
            "建议检查人物一致性",
            "建议优化对话节奏",
            "建议增强场景描写"
        ]

        # 简单评分逻辑（基于字数）
        word_count = len(chapter.content)
        score = min(100, max(60, word_count // 20))

        return ReviewResponse(
            chapter_number=chapter_number,
            suggestions=suggestions,
            score=score
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review failed: {str(e)}"
        )


@router.post(
    "/{novel_id}/outline/extend",
    response_model=ExtendOutlineResponse,
    status_code=status.HTTP_200_OK
)
async def extend_outline(
    novel_id: str,
    request: ExtendOutlineRequest,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow)
):
    """续写大纲：基于当前进度生成后续章节大纲"""
    try:
        # 使用 workflow 的 suggest_outline 为后续章节生成大纲
        outlines = []
        chapters_added = 0

        for i in range(request.count):
            chapter_num = request.from_chapter + i
            try:
                outline = await workflow.suggest_outline(novel_id, chapter_num)
                outlines.append(outline)
                chapters_added += 1
            except Exception as e:
                logger.warning(f"Failed to generate outline for chapter {chapter_num}: {e}")
                break

        return ExtendOutlineResponse(
            success=chapters_added > 0,
            chapters_added=chapters_added,
            outlines=outlines
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extend outline failed: {str(e)}"
        )


# ============================================================================
# Bible / Knowledge 一键 AI 生成（补齐旧小说数据）
# ============================================================================

class GenerateBibleResponse(BaseModel):
    success: bool
    message: str
    characters_count: int = 0
    locations_count: int = 0


class GenerateKnowledgeResponse(BaseModel):
    success: bool
    message: str
    facts_count: int = 0
    premise_lock: str = ""


@router.post(
    "/{novel_id}/bible/generate",
    response_model=GenerateBibleResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 生成 Bible 设定"
)
async def generate_bible(
    novel_id: str,
    bible_generator: AutoBibleGenerator = Depends(get_auto_bible_generator),
    novel_service=Depends(get_novel_service),
):
    """为指定小说 AI 生成（或重新生成）Bible 设定。

    - 会覆盖现有 Bible 中的角色、地点与文风数据
    - 需要 ANTHROPIC_API_KEY
    """
    try:
        novel = novel_service.get_novel(novel_id)
        if not novel:
            raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")

        bible_data = await bible_generator.generate_and_save(
            novel_id=novel_id,
            title=novel.title,
            target_chapters=novel.target_chapters,
        )

        chars = bible_data.get("characters", [])
        locs = bible_data.get("locations", [])
        return GenerateBibleResponse(
            success=True,
            message=f"Bible 生成成功：{len(chars)} 位角色，{len(locs)} 个地点",
            characters_count=len(chars),
            locations_count=len(locs),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_bible failed for %s", novel_id)
        raise HTTPException(status_code=500, detail=f"Bible 生成失败：{str(e)}")


@router.post(
    "/{novel_id}/knowledge/generate",
    response_model=GenerateKnowledgeResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 生成初始 Knowledge 知识图谱"
)
async def generate_knowledge(
    novel_id: str,
    knowledge_generator: AutoKnowledgeGenerator = Depends(get_auto_knowledge_generator),
    novel_service=Depends(get_novel_service),
    bible_service=Depends(get_bible_service),
):
    """为指定小说 AI 生成初始 Knowledge（梗概锁定 + 知识三元组）。

    - 会读取已有 Bible 作为参考
    - 需要 ANTHROPIC_API_KEY
    """
    try:
        novel = novel_service.get_novel(novel_id)
        if not novel:
            raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")

        # 尝试读取 Bible 摘要作为生成参考
        bible_summary = ""
        try:
            bible = bible_service.get_bible_by_novel(novel_id)
            if bible and bible.characters:
                char_desc = "、".join(
                    f"{c.name}" for c in list(bible.characters)[:5]
                )
                bible_summary = f"主要角色：{char_desc}。"
                if bible.locations:
                    loc_desc = "、".join(l.name for l in list(bible.locations)[:3])
                    bible_summary += f"重要地点：{loc_desc}。"
                if bible.style_notes:
                    bible_summary += f"文风：{list(bible.style_notes)[0].content[:80]}。"
        except Exception:
            pass

        knowledge_data = await knowledge_generator.generate_and_save(
            novel_id=novel_id,
            title=novel.title,
            bible_summary=bible_summary,
        )

        facts_count = len(knowledge_data.get("facts", []))
        premise = knowledge_data.get("premise_lock", "")
        return GenerateKnowledgeResponse(
            success=True,
            message=f"Knowledge 生成成功：梗概锁定已写入，{facts_count} 条知识三元组",
            facts_count=facts_count,
            premise_lock=premise[:120] + ("…" if len(premise) > 120 else ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_knowledge failed for %s", novel_id)
        raise HTTPException(status_code=500, detail=f"Knowledge 生成失败：{str(e)}")
