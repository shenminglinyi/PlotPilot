"""Small providers for context budget slots.

Keep repository lookups and prompt-block rendering out of the allocator so the
budget core can stay focused on slot ordering, compression, and assembly.
"""
from __future__ import annotations

import logging
from typing import Any

from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_role import StorylineRole

logger = logging.getLogger(__name__)


def build_narrative_promise_slot_content(
    novel_repository: Any,
    novel_id: str,
    chapter_number: int,
) -> str:
    """Build the compact narrative promise block for a novel.

    Returns an empty string when the dependency is unavailable or the source
    novel has no usable promise material. The caller decides whether the empty
    slot should still be registered.
    """
    if not novel_repository:
        return ""

    try:
        from application.world.services.narrative_promise import (
            build_narrative_promise_block,
        )

        novel = novel_repository.get_by_id(NovelId(novel_id))
        if not novel:
            return ""
        return build_narrative_promise_block(novel, chapter_number)
    except Exception as exc:
        logger.debug(
            "叙事承诺锁构建失败 novel=%s ch=%s: %s",
            novel_id,
            chapter_number,
            exc,
        )
        return ""


def build_storyline_slot_content(
    storyline_repository: Any,
    confluence_repository: Any,
    novel_id: str,
    chapter_number: int,
) -> str:
    """Build active storyline context, graded by distance to confluence."""
    if not storyline_repository or not confluence_repository:
        return ""

    storylines = storyline_repository.get_by_novel_id(NovelId(novel_id))
    confluences = confluence_repository.get_by_novel_id(novel_id)

    active = [
        storyline
        for storyline in storylines
        if storyline.estimated_chapter_start
        <= chapter_number
        <= storyline.estimated_chapter_end
        and storyline.chapter_weight > 0.05
    ]
    if not active:
        return ""

    role_order = {StorylineRole.MAIN: 0, StorylineRole.SUB: 1, StorylineRole.DARK: 2}
    active.sort(key=lambda storyline: role_order.get(storyline.role, 9))

    lines = ["━━━ 故事线上下文（本章活跃）━━━"]
    for storyline in active:
        lines.append(
            format_storyline_context_block(storyline, confluences, chapter_number)
        )

    return "\n".join(lines)


def format_storyline_context_block(
    storyline: Any,
    confluences: list[Any],
    chapter_number: int,
) -> str:
    """Format one storyline as a prompt block."""
    role_label = {"main": "主线", "sub": "支线", "dark": "暗线"}.get(
        storyline.role.value,
        storyline.role.value,
    )

    near = None
    min_dist = 9999
    for confluence in confluences:
        if confluence.source_storyline_id == storyline.id and not confluence.resolved:
            distance = confluence.target_chapter - chapter_number
            if 0 <= distance < min_dist:
                min_dist = distance
                near = confluence

    name_str = storyline.name or f"故事线 {storyline.id[:8]}"

    if (
        storyline.role == StorylineRole.DARK
        and near
        and near.merge_type == "reveal"
        and min_dist > 2
    ):
        lines = [f"\n● [暗线 ◎ 第{near.target_chapter}章揭露] 「{name_str}」"]
        if near.pre_reveal_hint:
            lines.append(f"  {near.pre_reveal_hint}")
        for guard in near.behavior_guards:
            lines.append(f"  禁忌：{guard}")
        return "\n".join(lines)

    if near:
        label_suffix = (
            f" ↘ 第{near.target_chapter}章汇"
            f"{'主线' if near.merge_type in ('absorb', 'intersect') else '线'}"
        )
    else:
        label_suffix = ""

    lines = [f"\n● [{role_label}] 「{name_str}」{label_suffix}"]

    if storyline.progress_summary:
        lines.append(f"  当前进度：{storyline.progress_summary}")

    current_ms = storyline.get_current_milestone()
    if current_ms:
        lines.append(f"  当前里程碑：{current_ms.description}")

    if near:
        if min_dist <= 2:
            lines.append(f"  ⚠️ 距汇流仅 {min_dist} 章！汇流内容：{near.context_summary}")
        elif min_dist <= 8:
            lines.append(f"  距汇流 {min_dist} 章，预期：{near.context_summary[:60]}…")

    return "\n".join(lines)
