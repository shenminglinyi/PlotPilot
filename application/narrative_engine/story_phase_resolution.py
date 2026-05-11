"""故事生命周期解析 — 与 `StoryPhaseDTO` / 四阶段模型对齐的单一真相源。"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def resolve_story_phase_payload(novel_id: str) -> Dict[str, Any]:
    """返回与 `StoryPhaseDTO` 字段一致的 dict（供 API 与叙事引擎门面复用）。"""
    novel = None
    try:
        from interfaces.api.dependencies import get_novel_service

        novel = get_novel_service().get_novel(novel_id)
        if novel and hasattr(novel, "story_phase"):
            phase = novel.story_phase
            phase_value = phase.value if hasattr(phase, "value") else str(phase)
            return {
                "phase": phase_value,
                "progress": float(getattr(phase, "progress", 0.0) or 0.0),
                "description": str(getattr(phase, "description", "") or ""),
                "can_advance": bool(getattr(phase, "can_advance", False)),
            }
    except Exception as e:
        logger.warning("resolve_story_phase: entity path failed novel=%s err=%s", novel_id, e)

    try:
        from domain.novel.value_objects.novel_id import NovelId
        from engine.core.entities.story import StoryPhase as StoryPhaseEnum
        from interfaces.api.dependencies import get_chapter_repository, get_novel_service

        novel = novel or get_novel_service().get_novel(novel_id)
        chapters = get_chapter_repository().list_by_novel(NovelId(novel_id))
        total = len(chapters) if chapters else 0
        target_raw = getattr(novel, "target_chapters", 30) if novel else 30
        try:
            target = int(target_raw or 30)
        except (TypeError, ValueError):
            target = 30
        if target <= 0:
            target = 30
        progress = min(1.0, total / target) if target > 0 else 0.0
        sp = StoryPhaseEnum.from_progress(progress)
        return {
            "phase": sp.value,
            "progress": round(progress, 3),
            "description": sp.description,
            "can_advance": sp != StoryPhaseEnum.FINALE,
        }
    except Exception as e:
        logger.warning("resolve_story_phase: fallback failed novel=%s err=%s", novel_id, e)
        return {
            "phase": "opening",
            "progress": 0.0,
            "description": "未知阶段",
            "can_advance": True,
        }
