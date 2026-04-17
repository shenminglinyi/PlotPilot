"""Chapter API 路由"""
import logging
from typing import List, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.core.services.chapter_service import ChapterService
from application.core.services.novel_service import NovelService
from application.core.dtos.chapter_dto import ChapterDTO
from application.core.dtos.novel_dto import NovelDTO
from application.audit.dtos.chapter_review_dto import ChapterReviewDTO
from application.core.dtos.chapter_structure_dto import ChapterStructureDTO
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from interfaces.api.dependencies import (
    get_chapter_service,
    get_novel_service,
    get_chapter_aftermath_pipeline,
)
from domain.shared.exceptions import EntityNotFoundError
logger = logging.getLogger(__name__)


async def _run_chapter_aftermath(
    novel_id: str,
    chapter_number: int,
    content: str,
    pipeline: ChapterAftermathPipeline,
) -> None:
    """与托管/守护进程同源的章后管线（叙事/向量、文风、KG；三元组与伏笔单次 LLM）。"""
    await pipeline.run_after_chapter_saved(novel_id, chapter_number, content)


router = APIRouter(tags=["chapters"])


# Request Models
class UpdateChapterContentRequest(BaseModel):
    """更新章节内容请求"""
    content: str = Field(..., min_length=0, max_length=100000, description="章节内容")
    generation_metrics: dict | None = Field(default=None, description="可选的生成质量控制指标")


class SaveChapterReviewRequest(BaseModel):
    """保存章节审阅请求"""
    status: Literal["draft", "reviewed", "approved"] = Field(..., description="审阅状态")
    memo: str = Field(default="", description="审阅备注")


class ChapterReviewResponse(BaseModel):
    """章节审阅响应"""
    status: str
    memo: str
    created_at: str
    updated_at: str


class ChapterStructureResponse(BaseModel):
    """章节结构响应"""
    word_count: int
    paragraph_count: int
    dialogue_ratio: float
    scene_count: int
    pacing: str


class ChapterGenerationMetricsResponse(BaseModel):
    novel_id: str
    chapter_number: int
    generated_via: str
    target: int
    actual: int
    tolerance: float
    delta: int
    status: str
    within_tolerance: bool
    action: str
    expansion_attempts: int
    trim_applied: bool
    fallback_used: bool
    min_allowed: int
    max_allowed: int
    created_at: str | None = None
    updated_at: str | None = None


class CreateChapterRequest(BaseModel):
    """创建章节请求"""
    chapter_id: str = Field(..., description="章节 ID")
    number: int = Field(..., gt=0, description="章节编号")
    title: str = Field(..., min_length=1, max_length=200, description="章节标题")
    content: str = Field(..., min_length=1, description="章节内容")


class EnsureChapterRequest(BaseModel):
    """确保章节存在请求（可选 title，不传则用「第N章」）"""
    title: str = Field(default="", max_length=200, description="章节标题（可选）")


# Routes
@router.get("/{novel_id}/chapters", response_model=List[ChapterDTO])
async def list_chapters(
    novel_id: str,
    service: ChapterService = Depends(get_chapter_service)
):
    """列出小说的所有章节

    Args:
        novel_id: 小说 ID
        service: Chapter 服务

    Returns:
        章节 DTO 列表
    """
    return service.list_chapters_by_novel(novel_id)


@router.post("/{novel_id}/chapters", response_model=NovelDTO, status_code=201)
async def create_chapter(
    novel_id: str,
    request: CreateChapterRequest,
    novel_service: NovelService = Depends(get_novel_service)
):
    """创建章节

    Args:
        novel_id: 小说 ID
        request: 创建章节请求
        novel_service: Novel 服务

    Returns:
        更新后的小说 DTO
    """
    try:
        return novel_service.add_chapter(
            novel_id=novel_id,
            chapter_id=request.chapter_id,
            number=request.number,
            title=request.title,
            content=request.content
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{novel_id}/chapters/{chapter_number}", response_model=ChapterDTO)
async def get_chapter(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """获取章节详情

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        章节 DTO

    Raises:
        HTTPException: 如果章节不存在
    """
    chapter = service.get_chapter_by_novel_and_number(novel_id, chapter_number)
    if chapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter not found: {novel_id}/chapter-{chapter_number}"
        )
    return chapter


@router.post("/{novel_id}/chapters/{chapter_number}/ensure", response_model=ChapterDTO)
async def ensure_chapter(
    novel_id: str,
    request: EnsureChapterRequest,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """确保章节在正文库中存在；若不存在则创建空白记录（不校验章节号连续性）。

    适用于结构树手动添加章节节点后、用户点击想直接开始写作的场景。
    """
    return service.ensure_chapter(novel_id, chapter_number, request.title)


@router.put("/{novel_id}/chapters/{chapter_number}", response_model=ChapterDTO)
async def update_chapter(
    novel_id: str,
    request: UpdateChapterContentRequest,
    background_tasks: BackgroundTasks,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service),
    pipeline: ChapterAftermathPipeline = Depends(get_chapter_aftermath_pipeline),
):
    """更新章节内容，保存成功后后台执行统一章后管线（见 ChapterAftermathPipeline）。"""
    try:
        chapter = service.update_chapter_by_novel_and_number(
            novel_id,
            chapter_number,
            request.content,
            request.generation_metrics,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{novel_id}/chapters/{chapter_number}/generation-metrics",
    response_model=ChapterGenerationMetricsResponse
)
async def get_chapter_generation_metrics(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    metrics = service.get_chapter_generation_metrics(novel_id, chapter_number)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Generation metrics not found: {novel_id}/chapter-{chapter_number}")
    return ChapterGenerationMetricsResponse(**metrics.__dict__)

    content = request.content
    background_tasks.add_task(
        _run_chapter_aftermath,
        novel_id,
        chapter_number,
        content,
        pipeline,
    )
    return chapter


@router.get("/{novel_id}/chapters/{chapter_number}/review", response_model=ChapterReviewResponse)
async def get_chapter_review(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """获取章节审阅

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        章节审阅信息

    Raises:
        HTTPException: 如果章节不存在
    """
    try:
        review = service.get_chapter_review(novel_id, chapter_number)
        return ChapterReviewResponse(
            status=review.status,
            memo=review.memo,
            created_at=review.created_at.isoformat(),
            updated_at=review.updated_at.isoformat()
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{novel_id}/chapters/{chapter_number}/review", response_model=ChapterReviewResponse)
async def save_chapter_review(
    novel_id: str,
    request: SaveChapterReviewRequest,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """保存章节审阅

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        request: 审阅请求
        service: Chapter 服务

    Returns:
        保存后的审阅信息

    Raises:
        HTTPException: 如果章节不存在
    """
    try:
        review = service.save_chapter_review(
            novel_id,
            chapter_number,
            request.status,
            request.memo
        )
        return ChapterReviewResponse(
            status=review.status,
            memo=review.memo,
            created_at=review.created_at.isoformat(),
            updated_at=review.updated_at.isoformat()
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{novel_id}/chapters/{chapter_number}/review-ai")
async def ai_review_chapter(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """AI 审阅章节

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        AI 审阅结果

    Raises:
        HTTPException: 如果章节不存在或内容为空
    """
    try:
        # 获取章节
        chapter = service.get_chapter_by_novel_and_number(novel_id, chapter_number)
        if chapter is None:
            raise HTTPException(status_code=404, detail=f"Chapter not found: {novel_id}/chapter-{chapter_number}")

        # 检查内容是否为空
        if not chapter.content or not chapter.content.strip():
            raise HTTPException(status_code=400, detail="Chapter content is empty")

        # TODO: 实现 AI 审阅逻辑
        # 这里需要集成 LLM 服务进行审阅
        return {
            "message": "AI review not yet implemented",
            "status": "pending"
        }
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{novel_id}/chapters/{chapter_number}/structure", response_model=ChapterStructureResponse)
async def get_chapter_structure(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """获取章节结构分析

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        章节结构分析

    Raises:
        HTTPException: 如果章节不存在
    """
    try:
        structure = service.get_chapter_structure(novel_id, chapter_number)
        return ChapterStructureResponse(
            word_count=structure.word_count,
            paragraph_count=structure.paragraph_count,
            dialogue_ratio=structure.dialogue_ratio,
            scene_count=structure.scene_count,
            pacing=structure.pacing
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
