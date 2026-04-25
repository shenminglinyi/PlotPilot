"""Bible API 路由"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Union
import logging

from application.world.services.bible_service import BibleService
from application.world.services.auto_bible_generator import AutoBibleGenerator
from application.world.services.auto_knowledge_generator import AutoKnowledgeGenerator
from application.world.dtos.bible_dto import BibleDTO
from interfaces.api.dependencies import (
    get_bible_service,
    get_auto_bible_generator,
    get_auto_knowledge_generator
)
from domain.shared.exceptions import EntityNotFoundError
from application.world.bible_generation_state import (
    clear_bible_generation_state,
    get_bible_generation_state,
    record_bible_generation_failure,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/bible", tags=["bible"])


# Request Models
class CreateBibleRequest(BaseModel):
    """创建 Bible 请求"""
    bible_id: str = Field(..., description="Bible ID")
    novel_id: str = Field(..., description="小说 ID")


class AddCharacterRequest(BaseModel):
    """添加人物请求"""
    character_id: str = Field(..., description="人物 ID")
    name: str = Field(..., description="人物名称")
    description: str = Field(..., description="人物描述")


class AddWorldSettingRequest(BaseModel):
    """添加世界设定请求"""
    setting_id: str = Field(..., description="设定 ID")
    name: str = Field(..., description="设定名称")
    description: str = Field(..., description="设定描述")
    setting_type: str = Field(..., description="设定类型")


class AddLocationRequest(BaseModel):
    """添加地点请求"""
    location_id: str = Field(..., description="地点 ID")
    name: str = Field(..., description="地点名称")
    description: str = Field(..., description="地点描述")
    location_type: str = Field(..., description="地点类型")
    parent_id: Optional[str] = Field(default=None, description="父地点 id，根为 null")


class AddTimelineNoteRequest(BaseModel):
    """添加时间线笔记请求"""
    note_id: str = Field(..., description="笔记 ID")
    event: str = Field(..., description="事件")
    time_point: str = Field(..., description="时间点")
    description: str = Field(..., description="描述")


class AddStyleNoteRequest(BaseModel):
    """添加风格笔记请求"""
    note_id: str = Field(..., description="笔记 ID")
    category: str = Field(..., description="类别")
    content: str = Field(..., description="内容")


class BibleCharacterRelationshipItem(BaseModel):
    """Bible 人物关系项（与 LLM 输出的 target/relation/description 对象一致）"""

    model_config = ConfigDict(extra="allow")

    target: Optional[str] = None
    relation: Optional[str] = None
    description: Optional[str] = None


class CharacterData(BaseModel):
    """人物数据"""
    id: str = Field(..., description="人物 ID")
    name: str = Field(..., description="人物名称")
    description: str = Field(..., description="人物描述")
    relationships: list[Union[str, BibleCharacterRelationshipItem]] = Field(
        default_factory=list,
        description="关系列表：字符串或结构化对象",
    )
    mental_state: Optional[str] = Field(
        default=None,
        description="心理状态；省略则保留库中旧值（新角色默认 NORMAL）",
    )
    verbal_tic: Optional[str] = Field(default=None, description="口头禅；省略则保留库中旧值")
    idle_behavior: Optional[str] = Field(
        default=None,
        description="待机动作/小动作；省略则保留库中旧值",
    )


class WorldSettingData(BaseModel):
    """世界设定数据"""
    id: str = Field(..., description="设定 ID")
    name: str = Field(..., description="设定名称")
    description: str = Field(..., description="设定描述")
    setting_type: str = Field(..., description="设定类型")


class LocationData(BaseModel):
    """地点数据"""
    id: str = Field(..., description="地点 ID")
    name: str = Field(..., description="地点名称")
    description: str = Field(..., description="地点描述")
    location_type: str = Field(..., description="地点类型")
    parent_id: Optional[str] = Field(default=None, description="父地点 id，根为 null")


class TimelineNoteData(BaseModel):
    """时间线笔记数据"""
    id: str = Field(..., description="笔记 ID")
    event: str = Field(..., description="事件")
    time_point: str = Field(..., description="时间点")
    description: str = Field(..., description="描述")


class StyleNoteData(BaseModel):
    """风格笔记数据"""
    id: str = Field(..., description="笔记 ID")
    category: str = Field(..., description="类别")
    content: str = Field(..., description="内容")


class BulkUpdateBibleRequest(BaseModel):
    """批量更新 Bible 请求"""
    characters: list[CharacterData] = Field(default_factory=list, description="人物列表")
    world_settings: list[WorldSettingData] = Field(default_factory=list, description="世界设定列表")
    locations: list[LocationData] = Field(default_factory=list, description="地点列表")
    timeline_notes: list[TimelineNoteData] = Field(default_factory=list, description="时间线笔记列表")
    style_notes: list[StyleNoteData] = Field(default_factory=list, description="风格笔记列表")


# Routes
@router.post("/novels/{novel_id}/generate", status_code=202)
async def generate_bible(
    novel_id: str,
    background_tasks: BackgroundTasks,
    stage: str = "all",  # all / worldbuilding / characters / locations
    bible_generator: AutoBibleGenerator = Depends(get_auto_bible_generator),
    knowledge_generator: AutoKnowledgeGenerator = Depends(get_auto_knowledge_generator)
):
    """手动触发 Bible 和 Knowledge 生成（异步）

    支持分阶段生成：
    - stage=all: 一次性生成所有内容（默认，向后兼容）
    - stage=worldbuilding: 只生成世界观（5维度）和文风公约
    - stage=characters: 基于已有世界观生成人物
    - stage=locations: 基于已有世界观和人物生成地点

    用户创建小说后，前端调用此接口开始生成 Bible。
    生成过程在后台进行，前端应轮询 /bible/novels/{novel_id}/bible/status 检查状态。

    Args:
        novel_id: 小说 ID
        stage: 生成阶段
        background_tasks: FastAPI 后台任务
        bible_generator: Bible 生成器
        knowledge_generator: Knowledge 生成器

    Returns:
        202 Accepted，表示生成任务已启动
    """
    async def _generate_task():
        logger.info("Bible generation task started for %s, stage=%s", novel_id, stage)
        clear_bible_generation_state(novel_id)
        try:
            # 获取小说信息（需要 premise 和 target_chapters）
            from interfaces.api.dependencies import get_novel_service
            novel_service = get_novel_service()
            novel = novel_service.get_novel(novel_id)
            if not novel:
                logger.error(f"Novel not found: {novel_id}")
                record_bible_generation_failure(novel_id, stage, "小说不存在，无法生成 Bible")
                return

            # 使用 premise（故事梗概）生成 Bible，如果没有则使用 title
            premise = novel.premise if novel.premise else novel.title

            # 生成 Bible（支持分阶段）
            bible_data = await bible_generator.generate_and_save(
                novel_id,
                premise,
                novel.target_chapters,
                stage=stage
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
                novel.title,
                bible_summary
            )
            logger.info(f"Bible and Knowledge generated successfully for {novel_id}")
            clear_bible_generation_state(novel_id)
        except Exception as e:
            import traceback
            logger.error("Bible generation task failed for %s: %s", novel_id, e)
            logger.error(traceback.format_exc())
            record_bible_generation_failure(novel_id, stage, str(e))

    background_tasks.add_task(_generate_task)

    return {
        "message": "Bible generation started",
        "novel_id": novel_id,
        "status_url": f"/api/v1/bible/novels/{novel_id}/bible/status"
    }


@router.post("/novels/{novel_id}/bible", response_model=BibleDTO, status_code=201)
async def create_bible(
    novel_id: str,
    request: CreateBibleRequest,
    service: BibleService = Depends(get_bible_service)
):
    """为小说创建 Bible

    Args:
        novel_id: 小说 ID
        request: 创建 Bible 请求
        service: Bible 服务

    Returns:
        创建的 Bible DTO
    """
    return service.create_bible(request.bible_id, novel_id)


# 注意：必须先注册比 `/novels/{id}/bible` 更长的路径，避免与 `{novel_id}` 匹配歧义
@router.get("/novels/{novel_id}/bible/generation-feedback")
async def get_bible_generation_feedback(novel_id: str):
    """新书向导轮询用：最近一次 Bible 异步生成失败原因（成功或未失败时为 null）。"""
    state = get_bible_generation_state(novel_id)
    if not state:
        return {"novel_id": novel_id, "error": None, "stage": None, "at": None}
    return {
        "novel_id": novel_id,
        "error": state.get("error"),
        "stage": state.get("stage"),
        "at": state.get("at"),
    }


@router.get("/novels/{novel_id}/bible/status")
async def get_bible_status(
    novel_id: str,
    service: BibleService = Depends(get_bible_service)
):
    """检查 Bible 生成状态

    Args:
        novel_id: 小说 ID
        service: Bible 服务

    Returns:
        状态信息：{ "exists": bool, "ready": bool }
    """
    try:
        bible = service.get_bible_by_novel(novel_id)
        exists = bible is not None
        # 修改ready逻辑：只要有文风公约或世界观就算ready（支持分阶段生成）
        ready = exists and (len(bible.style_notes) > 0 or len(bible.world_settings) > 0 or len(bible.characters) > 0)

        return {
            "exists": exists,
            "ready": ready,
            "novel_id": novel_id
        }
    except Exception as e:
        logger.exception("get_bible_status failed for novel_id=%s", novel_id)
        raise HTTPException(status_code=500, detail=f"检查 Bible 状态失败: {e}") from e


@router.get("/novels/{novel_id}/bible", response_model=BibleDTO)
async def get_bible_by_novel(
    novel_id: str,
    service: BibleService = Depends(get_bible_service)
):
    """获取小说的 Bible

    Args:
        novel_id: 小说 ID
        service: Bible 服务

    Returns:
        Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    bible = service.get_bible_by_novel(novel_id)
    if bible is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bible not found for novel: {novel_id}"
        )
    return bible


@router.get("/novels/{novel_id}/bible/characters", response_model=list)
async def list_characters(
    novel_id: str,
    service: BibleService = Depends(get_bible_service)
):
    """列出 Bible 中的所有人物

    Args:
        novel_id: 小说 ID
        service: Bible 服务

    Returns:
        人物 DTO 列表

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    bible = service.get_bible_by_novel(novel_id)
    if bible is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bible not found for novel: {novel_id}"
        )
    return bible.characters


@router.post("/novels/{novel_id}/bible/characters", response_model=BibleDTO)
async def add_character(
    novel_id: str,
    request: AddCharacterRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加人物到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加人物请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_character(
            novel_id=novel_id,
            character_id=request.character_id,
            name=request.name,
            description=request.description
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/world-settings", response_model=BibleDTO)
async def add_world_setting(
    novel_id: str,
    request: AddWorldSettingRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加世界设定到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加世界设定请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_world_setting(
            novel_id=novel_id,
            setting_id=request.setting_id,
            name=request.name,
            description=request.description,
            setting_type=request.setting_type
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/locations", response_model=BibleDTO)
async def add_location(
    novel_id: str,
    request: AddLocationRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加地点到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加地点请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_location(
            novel_id=novel_id,
            location_id=request.location_id,
            name=request.name,
            description=request.description,
            location_type=request.location_type,
            parent_id=request.parent_id,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/timeline-notes", response_model=BibleDTO)
async def add_timeline_note(
    novel_id: str,
    request: AddTimelineNoteRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加时间线笔记到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加时间线笔记请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_timeline_note(
            novel_id=novel_id,
            note_id=request.note_id,
            event=request.event,
            time_point=request.time_point,
            description=request.description
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/bible/style-notes", response_model=BibleDTO)
async def add_style_note(
    novel_id: str,
    request: AddStyleNoteRequest,
    service: BibleService = Depends(get_bible_service)
):
    """添加风格笔记到 Bible

    Args:
        novel_id: 小说 ID
        request: 添加风格笔记请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在
    """
    try:
        return service.add_style_note(
            novel_id=novel_id,
            note_id=request.note_id,
            category=request.category,
            content=request.content
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/novels/{novel_id}/bible", response_model=BibleDTO)
async def bulk_update_bible(
    novel_id: str,
    request: BulkUpdateBibleRequest,
    service: BibleService = Depends(get_bible_service)
):
    """批量更新 Bible 的所有数据

    Args:
        novel_id: 小说 ID
        request: 批量更新请求
        service: Bible 服务

    Returns:
        更新后的 Bible DTO

    Raises:
        HTTPException: 如果 Bible 不存在或参数无效
    """
    try:
        return service.update_bible(
            novel_id=novel_id,
            characters=request.characters,
            world_settings=request.world_settings,
            locations=request.locations,
            timeline_notes=request.timeline_notes,
            style_notes=request.style_notes
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
