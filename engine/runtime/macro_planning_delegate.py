"""宏观规划委托 — Phase 5 从 AutopilotDaemon 迁入 engine/runtime"""
from __future__ import annotations

import logging
from typing import Any

from domain.novel.entities.novel import Novel, NovelStage

logger = logging.getLogger(__name__)


async def run_macro_planning(host: Any, novel: Novel) -> None:
    """处理宏观规划（规划部/卷/幕）- 使用极速模式让 AI 自主推断结构"""
    if not host._is_still_running(novel):
        return

    host._update_shared_state(
        novel.novel_id.value,
        writing_substep="macro_planning",
        writing_substep_label="宏观规划",
    )

    target_chapters = novel.target_chapters or 30

    logger.info(
        "[%s] macro_planning start target_chapters=%s",
        novel.novel_id.value,
        target_chapters,
    )

    result = await host.planning_service.generate_macro_plan(
        novel_id=novel.novel_id.value,
        target_chapters=target_chapters,
        structure_preference=None,
    )

    ok = bool(result.get("success"))
    n_parts = len(result.get("structure") or []) if isinstance(result.get("structure"), list) else -1
    logger.info(
        "[%s] macro_planning generate_macro_plan returned success=%s parts=%s",
        novel.novel_id.value,
        ok,
        n_parts,
    )

    if not host._is_still_running(novel):
        logger.info("[%s] 宏观规划 LLM 返回后检测到停止，不再落库", novel.novel_id)
        return

    await host.planning_service.apply_macro_plan_from_llm_result(
        result,
        novel_id=novel.novel_id.value,
        target_chapters=target_chapters,
        allow_minimal_placeholder_on_empty=False,
    )

    if getattr(novel, "auto_approve_mode", False):
        novel.current_stage = NovelStage.ACT_PLANNING
        host._flush_novel(novel)
        host._sync_storylines_to_shared_memory(novel.novel_id.value)
        logger.info("[%s] 全自动模式：宏观规划完成，直接进入幕级规划", novel.novel_id)
    else:
        novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
        host._flush_novel(novel)
        host._sync_storylines_to_shared_memory(novel.novel_id.value)
        logger.info("[%s] 宏观规划完成，进入审阅等待", novel.novel_id)
