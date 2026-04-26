"""Novel API 路由"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import logging

from application.core.services.novel_service import NovelService
from application.world.services.auto_bible_generator import AutoBibleGenerator
from application.world.services.auto_knowledge_generator import AutoKnowledgeGenerator
from application.core.dtos.novel_dto import NovelDTO
from interfaces.api.dependencies import (
    get_novel_service,
    get_auto_bible_generator,
    get_auto_knowledge_generator
)
from domain.shared.exceptions import EntityNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["novels"])


# Request Models
class CreateNovelRequest(BaseModel):
    """创建小说请求"""
    novel_id: str = Field(..., description="小说 ID")
    title: str = Field(..., description="小说标题")
    author: str = Field(..., description="作者")
    target_chapters: int = Field(
        100,
        ge=0,
        description="目标章节数；选 V1 体量档时可传 0 由服务端推导",
    )
    premise: str = Field(default="", max_length=2000, description="故事梗概/创意（建议 2000 字内）")
    genre: str = Field(default="", description="赛道/类型（下拉预设）")
    world_preset: str = Field(default="", description="世界观基调（下拉预设）")
    length_tier: Optional[Literal["short", "standard", "epic"]] = Field(
        None,
        description="V1 目标篇幅档：short≈30万字 / standard≈100万字 / epic≈300万字（推导章数与每章字数）",
    )
    target_words_per_chapter: Optional[int] = Field(
        None,
        description="每章目标字数；可选，与体量档或自定义章数搭配",
    )


class UpdateStageRequest(BaseModel):
    """更新阶段请求"""
    stage: str = Field(..., description="小说阶段")


class UpdateNovelRequest(BaseModel):
    """更新小说基本信息请求"""
    title: str = Field(None, description="小说标题")
    author: str = Field(None, description="作者")
    target_chapters: int = Field(None, gt=0, description="目标章节数")
    premise: str = Field(None, description="故事梗概/创意")
    target_words_per_chapter: Optional[int] = Field(
        None,
        ge=500,
        le=10000,
        description="每章目标字数（全托管节拍与章长参考）",
    )


class UpdateAutoApproveRequest(BaseModel):
    """更新全自动模式请求"""
    auto_approve_mode: bool = Field(..., description="是否开启全自动模式（跳过所有人工审阅）")


async def _generate_bible_background(
    novel_id: str,
    title: str,
    target_chapters: int,
    bible_generator: AutoBibleGenerator,
    knowledge_generator: AutoKnowledgeGenerator
):
    """后台任务：生成 Bible 和 Knowledge"""
    bible_summary = ""
    try:
        bible_data = await bible_generator.generate_and_save(
            novel_id,
            title,
            target_chapters
        )
        # 构建 Bible 摘要供 Knowledge 生成使用
        chars = bible_data.get("characters", [])
        locs = bible_data.get("locations", [])
        char_desc = "、".join(f"{c['name']}（{c.get('role', '')}）" for c in chars[:5])
        loc_desc = "、".join(c['name'] for c in locs[:3])
        bible_summary = f"主要角色：{char_desc}。重要地点：{loc_desc}。文风：{bible_data.get('style', '')}。"

        # 生成初始 Knowledge
        await knowledge_generator.generate_and_save(
            novel_id,
            title,
            bible_summary
        )
        logger.info(f"Bible and Knowledge generated successfully for {novel_id}")
    except Exception as e:
        logger.error(f"Failed to generate Bible/Knowledge for {novel_id}: {e}")


# Routes
@router.post("/", response_model=NovelDTO, status_code=201)
async def create_novel(
    request: CreateNovelRequest,
    service: NovelService = Depends(get_novel_service)
):
    """创建新小说（不自动生成 Bible）

    创建小说后，前端应该：
    1. 调用 POST /bible/novels/{novel_id}/generate 触发 Bible 生成
    2. 轮询 GET /bible/novels/{novel_id}/bible/status 检查生成状态
    3. 引导用户确认 Bible
    4. 用户手动触发规划（通过 POST /novels/{novel_id}/structure/plan 接口）

    Args:
        request: 创建小说请求
        service: Novel 服务

    Returns:
        创建的小说 DTO
    """
    # 只创建小说实体，不生成 Bible
    novel_dto = service.create_novel(
        novel_id=request.novel_id,
        title=request.title,
        author=request.author,
        target_chapters=request.target_chapters,
        premise=request.premise,
        genre=request.genre,
        world_preset=request.world_preset,
        length_tier=request.length_tier,
        target_words_per_chapter=request.target_words_per_chapter,
    )

    return novel_dto


@router.get("/{novel_id}", response_model=NovelDTO)
async def get_novel(
    novel_id: str,
    service: NovelService = Depends(get_novel_service)
):
    """获取小说详情

    Args:
        novel_id: 小说 ID
        service: Novel 服务

    Returns:
        小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    novel = service.get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")
    return novel


@router.get("/", response_model=List[NovelDTO])
async def list_novels(service: NovelService = Depends(get_novel_service)):
    """列出所有小说

    Args:
        service: Novel 服务

    Returns:
        小说 DTO 列表
    """
    return service.list_novels()


@router.put("/{novel_id}", response_model=NovelDTO)
async def update_novel(
    novel_id: str,
    request: UpdateNovelRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新小说基本信息

    Args:
        novel_id: 小说 ID
        request: 更新小说请求
        service: Novel 服务

    Returns:
        更新后的小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_novel(
            novel_id,
            request.title,
            request.author,
            request.target_chapters,
            request.premise,
            target_words_per_chapter=request.target_words_per_chapter,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{novel_id}/stage", response_model=NovelDTO)
async def update_novel_stage(
    novel_id: str,
    request: UpdateStageRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新小说阶段

    Args:
        novel_id: 小说 ID
        request: 更新阶段请求
        service: Novel 服务

    Returns:
        更新后的小说 DTO

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_novel_stage(novel_id, request.stage)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{novel_id}", status_code=204)
async def delete_novel(
    novel_id: str,
    service: NovelService = Depends(get_novel_service)
):
    """删除小说

    Args:
        novel_id: 小说 ID
        service: Novel 服务
    """
    service.delete_novel(novel_id)


@router.post("/{novel_id}/bible/generate", status_code=202)
async def generate_bible_alias(
    novel_id: str,
    background_tasks: BackgroundTasks,
    stage: str = "all",
    bible_generator: AutoBibleGenerator = Depends(get_auto_bible_generator),
    knowledge_generator: AutoKnowledgeGenerator = Depends(get_auto_knowledge_generator)
):
    """手动触发 Bible 生成（别名路由，与 POST /bible/novels/{novel_id}/generate 等价）

    Args:
        novel_id: 小说 ID
        background_tasks: FastAPI 后台任务
        stage: 生成阶段 (all / worldbuilding / characters / locations)

    Returns:
        202 Accepted
    """
    try:
        import traceback

        async def _generate_task():
            try:
                bible_data = await bible_generator.generate_and_save(
                    novel_id=novel_id,
                    stage=stage
                )
                if knowledge_generator and stage in ("all", "worldbuilding"):
                    await knowledge_generator.generate_and_save(
                        novel_id=novel_id,
                        bible_data=bible_data
                    )
            except Exception as e:
                logger.error(f"Failed to generate Bible/Knowledge for {novel_id}: {e}")
                logger.error(traceback.format_exc())

        background_tasks.add_task(_generate_task)

        return {
            "message": "Bible generation started",
            "novel_id": novel_id,
            "status_url": f"/api/v1/bible/novels/{novel_id}/bible/status"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动Bible生成失败: {str(e)}")


@router.patch("/{novel_id}/auto-approve-mode", response_model=NovelDTO)
async def update_auto_approve_mode(
    novel_id: str,
    request: UpdateAutoApproveRequest,
    service: NovelService = Depends(get_novel_service)
):
    """更新全自动模式设置
    
    Args:
        novel_id: 小说 ID
        request: 更新全自动模式请求
        service: Novel 服务
        
    Returns:
        更新后的小说 DTO
        
    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.update_auto_approve_mode(novel_id, request.auto_approve_mode)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{novel_id}/statistics")
async def get_novel_statistics(
    novel_id: str,
    service: NovelService = Depends(get_novel_service)
):
    """获取小说统计信息

    Args:
        novel_id: 小说 ID
        service: Novel 服务

    Returns:
        统计信息字典

    Raises:
        HTTPException: 如果小说不存在
    """
    try:
        return service.get_novel_statistics(novel_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
