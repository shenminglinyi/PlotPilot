"""叙事引擎 HTTP 面 — 小说家维度的只读聚合，底层复用 QueryService / 沙盒 / Bible。"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from application.engine.services.query_service import get_query_service
from application.narrative_engine.api_catalog import build_surface_catalog_payload
from application.narrative_engine.read_facade import NarrativeEngineReadFacade
from interfaces.api.dependencies import get_narrative_engine_read_facade

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["narrative-engine"])

surface_router = APIRouter(prefix="/narrative-engine", tags=["narrative-engine"])


@surface_router.get("/surface-catalog")
async def get_surface_catalog() -> Dict[str, Any]:
    """全站 API 能力族目录（小说家维度 × 前端模块 × 路径前缀）。

    供 IDE、契约测试与文档生成消费；不要求 novel_id。
    """
    return build_surface_catalog_payload()


@router.get("/{novel_id}/narrative-engine/story-evolution")
async def get_story_evolution_read_model(
    novel_id: str,
    facade: NarrativeEngineReadFacade = Depends(get_narrative_engine_read_facade),
) -> Dict[str, Any]:
    """一书一页：生命周期 × 故事线/弧光 × 编年史 × 章节 digest。

    与右栏「故事演进」三列数据源对齐；可替代多次并行 GET。
    """
    if get_query_service().get_novel_status(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        return facade.get_story_evolution_read_model(novel_id)
    except Exception as e:
        logger.error("narrative-engine story-evolution failed novel=%s err=%s", novel_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="narrative_engine_read_failed") from e


@router.get("/{novel_id}/narrative-engine/persona-voice/{character_id}")
async def get_persona_voice_read_model(
    novel_id: str,
    character_id: str,
    facade: NarrativeEngineReadFacade = Depends(get_narrative_engine_read_facade),
) -> Dict[str, Any]:
    """单角一线：声线锚点 + 对白语料统计（与「角色对话」右栏语义对齐）。"""
    if get_query_service().get_novel_status(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        return facade.get_persona_voice_read_model(novel_id, character_id)
    except ValueError as e:
        code = str(e)
        if code == "bible_not_found":
            raise HTTPException(status_code=404, detail="Bible not found") from e
        if code == "character_not_found":
            raise HTTPException(status_code=404, detail="Character not found") from e
        raise HTTPException(status_code=400, detail=code) from e
    except Exception as e:
        logger.error(
            "narrative-engine persona-voice failed novel=%s char=%s err=%s",
            novel_id,
            character_id,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="narrative_engine_read_failed") from e
