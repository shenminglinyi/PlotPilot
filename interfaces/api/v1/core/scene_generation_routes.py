"""场景生成 API 路由"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from application.core.services.scene_generation_service import SceneGenerationService
from application.blueprint.services.beat_sheet_service import BeatSheetService
from domain.novel.value_objects.scene import Scene
from interfaces.api.dependencies import get_scene_generation_service, get_beat_sheet_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenes", tags=["scenes"])


class GenerateSceneRequest(BaseModel):
    """生成场景请求"""
    chapter_id: str = Field(..., description="章节 ID")
    chapter_number: int = Field(..., ge=1, description="章节号")
    scene_index: int = Field(..., ge=0, description="场景索引（从 0 开始）")


class GenerateSceneResponse(BaseModel):
    """生成场景响应"""
    scene_title: str
    scene_index: int
    content: str
    word_count: int


@router.post("/generate", response_model=GenerateSceneResponse)
async def generate_scene(
    request: GenerateSceneRequest,
    scene_gen_service: SceneGenerationService = Depends(get_scene_generation_service),
    beat_sheet_service: BeatSheetService = Depends(get_beat_sheet_service)
):
    """为指定场景生成正文

    根据节拍表中的场景信息生成 500-1000 字的正文
    """
    try:
        # 1. 获取节拍表
        beat_sheet = await beat_sheet_service.get_beat_sheet(request.chapter_id)
        if not beat_sheet:
            raise HTTPException(
                status_code=404,
                detail=f"Beat sheet not found for chapter {request.chapter_id}"
            )

        # 2. 获取目标场景
        if request.scene_index >= len(beat_sheet.scenes):
            raise HTTPException(
                status_code=400,
                detail=f"Scene index {request.scene_index} out of range (total: {len(beat_sheet.scenes)})"
            )

        target_scene = beat_sheet.scenes[request.scene_index]

        # 3. 获取前置场景（如果有）
        previous_scenes = []
        # TODO: 从数据库读取已生成的前置场景正文
        # 当前简化版：暂时传空列表

        # 4. 生成场景正文
        content = await scene_gen_service.generate_scene(
            scene=target_scene,
            chapter_number=request.chapter_number,
            previous_scenes=previous_scenes,
            bible_context=None  # TODO: 获取 Bible 上下文
        )

        return GenerateSceneResponse(
            scene_title=target_scene.title,
            scene_index=request.scene_index,
            content=content,
            word_count=len(content)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate scene: {e}")
        raise HTTPException(status_code=500, detail=str(e))
