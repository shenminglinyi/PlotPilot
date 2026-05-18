"""结构树与 ``chapters`` 正文表对齐：以 ``story_nodes`` 中的章节节点为准。

规则：结构上不存在的章节号，正文表也不保留（树上的章删了，正文占位一并消失），新章顺延编号。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Set

from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.novel_id import NovelId

if TYPE_CHECKING:
    from domain.novel.repositories.chapter_repository import ChapterRepository
    from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

logger = logging.getLogger(__name__)


def collect_structure_chapter_numbers(
    story_node_repo: "StoryNodeRepository",
    novel_id: str,
) -> Set[int]:
    """全书结构树上 chapter 节点的全局章节号集合。"""
    nums: Set[int] = set()
    for n in story_node_repo.get_by_novel_sync(novel_id):
        if not n.is_chapter():
            continue
        try:
            nums.add(int(n.number))
        except (TypeError, ValueError):
            continue
    return nums


def purge_chapter_book_rows_not_matching_structure(
    story_node_repo: "StoryNodeRepository",
    chapter_repository: Optional["ChapterRepository"],
    novel_id: str,
) -> int:
    """删除正文表中「树上的 chapter 列表里不存在同名章号」的所有行。

    Returns:
        删除的行数
    """
    if chapter_repository is None:
        return 0
    structure_nums = collect_structure_chapter_numbers(story_node_repo, novel_id)
    novel_vo = NovelId(novel_id)
    removed = 0
    for ch in list(chapter_repository.list_by_novel(novel_vo)):
        try:
            cn = int(ch.number)
        except (TypeError, ValueError):
            continue
        if cn in structure_nums:
            continue
        cid = getattr(ch.id, "value", ch.id)
        text_preview = len((ch.content or "").strip())
        if text_preview:
            logger.warning(
                "[chapter↔structure] novel=%s 删正文行 #%s (%s)：树无章节点，按要求同步删除（正文约 %s 字）",
                novel_id,
                cn,
                cid,
                text_preview,
            )
        chapter_repository.delete(ChapterId(cid))
        removed += 1
    if removed:
        logger.info("[chapter↔structure] novel=%s 已删与树不一致的正文行 %s 条", novel_id, removed)
    return removed
