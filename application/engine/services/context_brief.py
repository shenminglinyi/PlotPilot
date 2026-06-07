"""Natural-language context brief builders for chapter generation."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def get_chapter_generation_hint(novel_id: str, chapter_number: int) -> str:
    """Load the author's chapter-specific generation hint."""
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import DatabaseConnection

        db = DatabaseConnection(str(get_db_path()))
        row = db.fetch_one(
            "SELECT generation_hint FROM chapters WHERE novel_id=? AND number=?",
            (novel_id, chapter_number),
        )
        if row:
            return (row["generation_hint"] or "").strip()
    except Exception:
        pass
    return ""


def build_bridge_hint(novel_id: str, chapter_number: int) -> str:
    """Render a soft continuation hint from the previous chapter bridge."""
    try:
        from application.engine.services.chapter_bridge_service import ChapterBridgeService
        from application.paths import get_db_path

        svc = ChapterBridgeService(db_path=str(get_db_path()))
        prev_bridge = svc.get_prev_chapter_bridge(novel_id, chapter_number)
        if not prev_bridge:
            return ""

        hints = []
        if prev_bridge.suspense_hook:
            hints.append(f"上一章留了悬念：{prev_bridge.suspense_hook}")
        if prev_bridge.emotional_residue:
            hints.append(f"主角情绪：{prev_bridge.emotional_residue}")
        if prev_bridge.scene_state:
            hints.append(f"场景：{prev_bridge.scene_state}")
        if prev_bridge.unfinished_actions:
            hints.append(f"未完成：{prev_bridge.unfinished_actions}")

        if not hints:
            return ""

        return "衔接：" + "；".join(hints) + "。你可以自然接续，也可以时间跳跃或视角切换。"

    except Exception as e:
        logger.debug("衔接提示获取失败: %s", e)
        return ""


def build_character_state_hint(context_assembler: Any, novel_id: str) -> str:
    """Compress structured character state into two or three prose hints."""
    if not context_assembler:
        return ""

    try:
        scars_content = context_assembler.build_scars_and_motivations(novel_id)
        if not scars_content or not scars_content.strip():
            return ""

        lines = [line.strip() for line in scars_content.split("\n") if line.strip()]
        content_lines = [
            line
            for line in lines
            if not line.startswith("【")
            and not line.startswith("═")
            and not line.startswith("━━")
        ]

        if not content_lines:
            return ""

        brief_lines = content_lines[:3]
        return "角色状态：" + "；".join(line.rstrip("。") for line in brief_lines if line) + "。"

    except Exception as e:
        logger.debug("角色状态概要获取失败: %s", e)
        return ""


def build_debt_hint(
    context_assembler: Any,
    novel_id: str,
    chapter_number: int,
    outline: str,
) -> str:
    """Compress narrative debt into a gentle editorial reminder."""
    if not context_assembler:
        return ""

    try:
        debt_content = context_assembler.build_debt_due_block(
            novel_id, chapter_number, outline
        )
        if not debt_content or not debt_content.strip():
            return ""

        lines = [line.strip() for line in debt_content.split("\n") if line.strip()]
        debt_lines = [line for line in lines if line.startswith("-") or line.startswith("•")]

        if not debt_lines:
            return ""

        brief_debts = [line.lstrip("-• ").rstrip() for line in debt_lines[:2]]
        return "叙事备忘：" + "；".join(brief_debts) + "。如果合适可以推进，不必强求回收。"

    except Exception as e:
        logger.debug("叙事备忘获取失败: %s", e)
        return ""


def build_context_brief(
    *,
    context_assembler: Any,
    novel_id: str,
    chapter_number: int,
    outline: str,
    generation_hint_loader: Callable[[str, int], str] = get_chapter_generation_hint,
    bridge_hint_builder: Callable[[str, int], str] = build_bridge_hint,
) -> str:
    """Build the natural-language editor note used by the V9 context budget."""
    parts = []

    user_hint = generation_hint_loader(novel_id, chapter_number)
    if user_hint:
        parts.append(f"【作者指令】{user_hint}")

    if chapter_number > 1:
        bridge_hint = bridge_hint_builder(novel_id, chapter_number)
        if bridge_hint:
            parts.append(bridge_hint)

    character_state_hint = build_character_state_hint(context_assembler, novel_id)
    if character_state_hint:
        parts.append(character_state_hint)

    debt_hint = build_debt_hint(context_assembler, novel_id, chapter_number, outline)
    if debt_hint:
        parts.append(debt_hint)

    if not parts:
        return ""

    return "【编辑手记】\n" + "\n".join(parts)
