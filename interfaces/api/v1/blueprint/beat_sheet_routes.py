"""节拍表 API 路由"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from application.blueprint.services.beat_sheet_service import BeatSheetService
from interfaces.api.dependencies import get_beat_sheet_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beat-sheets", tags=["beat-sheets"])


class SceneResponse(BaseModel):
    """场景响应模型"""
    title: str
    goal: str
    pov_character: str
    location: Optional[str]
    tone: Optional[str]
    estimated_words: int
    order_index: int


class BeatSheetResponse(BaseModel):
    """节拍表响应模型"""
    id: str
    chapter_id: str
    scenes: List[SceneResponse]
    total_scenes: int
    total_estimated_words: int


class GenerateBeatSheetRequest(BaseModel):
    """生成节拍表请求"""
    chapter_id: str = Field(..., description="章节 ID")
    outline: str = Field(..., description="章节大纲")


@router.post("/generate", response_model=BeatSheetResponse)
async def generate_beat_sheet(
    request: GenerateBeatSheetRequest,
    service: BeatSheetService = Depends(get_beat_sheet_service)
):
    """为章节生成节拍表

    根据章节大纲生成 3-5 个场景，每个场景包含：
    - 场景标题
    - 场景目标
    - POV 角色
    - 地点（可选）
    - 情绪基调（可选）
    - 预估字数
    """
    try:
        beat_sheet = await service.generate_beat_sheet(
            chapter_id=request.chapter_id,
            outline=request.outline
        )

        return BeatSheetResponse(
            id=beat_sheet.id,
            chapter_id=beat_sheet.chapter_id,
            scenes=[
                SceneResponse(
                    title=scene.title,
                    goal=scene.goal,
                    pov_character=scene.pov_character,
                    location=scene.location,
                    tone=scene.tone,
                    estimated_words=scene.estimated_words,
                    order_index=scene.order_index
                )
                for scene in beat_sheet.scenes
            ],
            total_scenes=beat_sheet.get_scene_count(),
            total_estimated_words=beat_sheet.get_total_estimated_words()
        )
    except Exception as e:
        logger.error(f"Failed to generate beat sheet: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{chapter_id}", response_model=BeatSheetResponse)
async def get_beat_sheet(
    chapter_id: str,
    service: BeatSheetService = Depends(get_beat_sheet_service)
):
    """获取章节的节拍表"""
    try:
        beat_sheet = await service.get_beat_sheet(chapter_id)
        if not beat_sheet:
            raise HTTPException(status_code=404, detail="Beat sheet not found")

        return BeatSheetResponse(
            id=beat_sheet.id,
            chapter_id=beat_sheet.chapter_id,
            scenes=[
                SceneResponse(
                    title=scene.title,
                    goal=scene.goal,
                    pov_character=scene.pov_character,
                    location=scene.location,
                    tone=scene.tone,
                    estimated_words=scene.estimated_words,
                    order_index=scene.order_index
                )
                for scene in beat_sheet.scenes
            ],
            total_scenes=beat_sheet.get_scene_count(),
            total_estimated_words=beat_sheet.get_total_estimated_words()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get beat sheet: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{chapter_id}")
async def delete_beat_sheet(
    chapter_id: str,
    service: BeatSheetService = Depends(get_beat_sheet_service)
):
    """删除章节的节拍表"""
    try:
        await service.delete_beat_sheet(chapter_id)
        return {"success": True, "message": "Beat sheet deleted"}
    except Exception as e:
        logger.error(f"Failed to delete beat sheet: {e}")
        raise HTTPException(status_code=500, detail=str(e))
