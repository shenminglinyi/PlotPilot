"""Small providers for context budget slots.

Keep repository lookups and prompt-block rendering out of the allocator so the
budget core can stay focused on slot ordering, compression, and assembly.
"""
from __future__ import annotations

import logging
from typing import Any

from domain.novel.value_objects.novel_id import NovelId

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
