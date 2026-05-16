from __future__ import annotations
from typing import List
from domain.shared.base_entity import BaseEntity

VALID_MERGE_TYPES = frozenset({"intersect", "absorb", "reveal"})


class ConfluencePoint(BaseEntity):
    """汇流点 —— 支线/暗线在指定章节并入目标线的 DAG merge event。

    merge_type 语义：
      intersect  两线交叉推进，支线不消亡，继续独立活跃
      absorb     支线被主线吸收，该支线 status → COMPLETED
      reveal     暗线在此章首次显现/揭露（配合 behavior_guards 使用）
    """

    def __init__(
        self,
        id: str,
        novel_id: str,
        source_storyline_id: str,
        target_storyline_id: str,
        target_chapter: int,
        merge_type: str,
        context_summary: str,
        pre_reveal_hint: str = "",
        behavior_guards: List[str] = None,
        resolved: bool = False,
    ):
        super().__init__(id)
        if merge_type not in VALID_MERGE_TYPES:
            raise ValueError(f"merge_type must be one of {VALID_MERGE_TYPES}, got {merge_type!r}")
        self.novel_id = novel_id
        self.source_storyline_id = source_storyline_id
        self.target_storyline_id = target_storyline_id
        self.target_chapter = target_chapter
        self.merge_type = merge_type
        self.context_summary = context_summary
        self.pre_reveal_hint = pre_reveal_hint
        self.behavior_guards: List[str] = behavior_guards if behavior_guards is not None else []
        self.resolved = resolved
