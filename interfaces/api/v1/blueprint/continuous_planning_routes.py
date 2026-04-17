"""
统一的故事规划 API 路由

整合宏观规划、幕级规划、AI 续规划
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

from application.blueprint.services.continuous_planning_service import (
    ContinuousPlanningService,
    MergeConflictException,
    get_macro_plan_progress,
    get_macro_plan_result,
)
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from domain.ai.services.llm_service import LLMService
from application.paths import get_db_path
from interfaces.api.dependencies import get_database


router = APIRouter(prefix="/api/v1/planning", tags=["continuous-planning"])


# ==================== DTOs ====================

class StructurePreference(BaseModel):
    """结构偏好"""
    parts: int = Field(3, ge=1, le=10)
    volumes_per_part: int = Field(3, ge=1, le=10)
    acts_per_volume: int = Field(3, ge=1, le=10)


class MacroPlanRequest(BaseModel):
    """宏观规划请求"""
    target_chapters: int = Field(100, ge=10, le=1000)
    structure: StructurePreference = Field(default_factory=StructurePreference)


class MacroPlanConfirmRequest(BaseModel):
    """宏观规划确认请求"""
    structure: List[Dict] = Field(..., description="用户编辑后的结构")


class ActChaptersRequest(BaseModel):
    """幕级规划请求"""
    chapter_count: Optional[int] = Field(None, ge=3, le=20)


class ActChaptersConfirmRequest(BaseModel):
    """幕级规划确认请求"""
    chapters: List[Dict] = Field(..., description="用户编辑后的章节列表")


class ContinuePlanningRequest(BaseModel):
    """续规划请求"""
    current_chapter: int = Field(..., ge=1)


# ==================== 依赖注入 ====================

def get_service() -> ContinuousPlanningService:
    """获取规划服务"""
    db_path = get_db_path()
    story_node_repo = StoryNodeRepository(db_path)
    chapter_element_repo = ChapterElementRepository(db_path)

    # 获取 LLM 服务
    import os
    from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
    from infrastructure.ai.config.settings import Settings

    llm_service = None
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    if api_key:
        settings = Settings(
            api_key=api_key.strip(),
            base_url=os.getenv("ANTHROPIC_BASE_URL")
        )
        try:
            llm_service = AnthropicProvider(settings)
        except Exception:
            pass

    from application.world.services.bible_service import BibleService
    from interfaces.api.dependencies import get_bible_repository

    bible_service = BibleService(get_bible_repository())

    return ContinuousPlanningService(
        story_node_repo,
        chapter_element_repo,
        llm_service,
        bible_service,
        chapter_repository=SqliteChapterRepository(get_database()),
    )


# ==================== 宏观规划 API ====================

@router.post("/novels/{novel_id}/macro/generate", status_code=202)
async def generate_macro_plan(
    novel_id: str,
    request: MacroPlanRequest,
    background_tasks: BackgroundTasks,
    service: ContinuousPlanningService = Depends(get_service)
):
    """生成宏观规划

    生成部-卷-幕结构框架，不保存，返回供用户编辑
    """
    try:
        logger.debug(f"路由层: 收到请求 novel_id={novel_id}, request={request}")
        service.initialize_macro_plan_task(novel_id)

        async def _generate_task():
            try:
                result = await service.generate_macro_plan(
                    novel_id=novel_id,
                    target_chapters=request.target_chapters,
                    structure_preference=request.structure.dict()
                )
                service.store_macro_plan_result(novel_id, result)
            except Exception as e:
                import traceback
                logger.error(f"生成宏观规划失败:\n{traceback.format_exc()}")
                service.store_macro_plan_error(novel_id, str(e))
                service._update_macro_progress(
                    novel_id,
                    status="failed",
                    message=f"结构规划生成失败: {e}",
                )

        background_tasks.add_task(_generate_task)
        return {
            "success": True,
            "task_started": True,
            "novel_id": novel_id,
        }
    except Exception as e:
        import traceback
        logger.error(f"生成宏观规划失败:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"生成宏观规划失败: {str(e)}")


@router.get("/novels/{novel_id}/macro/progress")
async def get_macro_plan_generation_progress(novel_id: str):
    """获取精密结构规划的实时进度。"""
    return {
        "success": True,
        "data": get_macro_plan_progress(novel_id)
    }


@router.get("/novels/{novel_id}/macro/result")
async def get_macro_plan_generation_result(novel_id: str):
    """获取精密结构规划生成结果。"""
    return {
        "success": True,
        "data": get_macro_plan_result(novel_id)
    }


@router.post("/novels/{novel_id}/macro/confirm")
async def confirm_macro_plan(
    novel_id: str,
    request: MacroPlanConfirmRequest,
    service: ContinuousPlanningService = Depends(get_service)
):
    """确认宏观规划（安全版本，带智能合并）

    用户编辑后，保存所有部-卷-幕节点（不创建章节）

    安全机制：
    - 绿色通路：纯空框架覆盖
    - 黄色通路：安全合并（保留已写正文）
    - 红色阻断：冲突检测（试图删除包含正文的节点）
    """
    try:
        result = await service.confirm_macro_plan_safe(
            novel_id=novel_id,
            structure=request.structure
        )
        return result
    except MergeConflictException as e:
        # 红色阻断：返回 409 Conflict 状态码
        raise HTTPException(
            status_code=409,
            detail={
                "error": "MERGE_CONFLICT",
                "message": str(e),
                "conflicts": e.conflicts
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"确认宏观规划失败: {str(e)}")


# ==================== 幕级规划 API ====================

@router.post("/acts/{act_id}/chapters/generate")
async def generate_act_chapters(
    act_id: str,
    request: ActChaptersRequest,
    service: ContinuousPlanningService = Depends(get_service)
):
    """为指定幕生成章节规划

    生成章节标题、大纲、关联 Bible 元素，不保存，返回供用户编辑
    """
    try:
        result = await service.plan_act_chapters(
            act_id=act_id,
            custom_chapter_count=request.chapter_count
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成章节规划失败: {str(e)}")


@router.post("/acts/{act_id}/chapters/confirm")
async def confirm_act_chapters(
    act_id: str,
    request: ActChaptersConfirmRequest,
    service: ContinuousPlanningService = Depends(get_service)
):
    """确认幕级规划

    用户编辑后，创建章节节点和元素关联
    """
    try:
        result = await service.confirm_act_planning(
            act_id=act_id,
            chapters=request.chapters
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"确认章节规划失败: {str(e)}")


# ==================== AI 续规划 API ====================

@router.post("/novels/{novel_id}/continue")
async def continue_planning(
    novel_id: str,
    request: ContinuePlanningRequest,
    service: ContinuousPlanningService = Depends(get_service)
):
    """AI 续规划

    写完章节后自动调用，判断当前幕是否完成，是否需要创建新幕
    """
    try:
        result = await service.continue_planning(
            novel_id=novel_id,
            current_chapter_number=request.current_chapter
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"续规划失败: {str(e)}")


@router.post("/acts/{act_id}/create-next")
async def create_next_act(
    act_id: str,
    service: ContinuousPlanningService = Depends(get_service)
):
    """创建下一幕

    当 AI 续规划提示需要新幕时，用户确认后调用
    """
    try:
        act = await service.story_node_repo.get_by_id(act_id)
        if not act:
            raise HTTPException(status_code=404, detail="幕节点不存在")

        result = await service.create_next_act_auto(
            novel_id=act.novel_id,
            current_act_id=act_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建下一幕失败: {str(e)}")


# ==================== 查询 API ====================

@router.get("/novels/{novel_id}/structure")
async def get_novel_structure(
    novel_id: str,
    service: ContinuousPlanningService = Depends(get_service)
):
    """获取小说的完整结构树"""
    try:
        tree = await service.story_node_repo.get_tree(novel_id)
        return {
            "success": True,
            "data": tree.to_hierarchical_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取结构树失败: {str(e)}")


@router.get("/acts/{act_id}")
async def get_act_detail(
    act_id: str,
    service: ContinuousPlanningService = Depends(get_service)
):
    """获取幕的详细信息"""
    try:
        act = await service.story_node_repo.get_by_id(act_id)
        if not act:
            raise HTTPException(status_code=404, detail="幕不存在")

        return {
            "success": True,
            "data": act.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取幕详情失败: {str(e)}")


@router.get("/chapters/{chapter_id}")
async def get_chapter_detail(
    chapter_id: str,
    service: ContinuousPlanningService = Depends(get_service)
):
    """获取章节的详细信息"""
    try:
        chapter = await service.story_node_repo.get_by_id(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="章节不存在")

        # 获取关联的元素
        elements = await service.chapter_element_repo.get_by_chapter(chapter_id)

        return {
            "success": True,
            "data": {
                "chapter": chapter.to_dict(),
                "elements": [elem.to_dict() for elem in elements]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节详情失败: {str(e)}")
