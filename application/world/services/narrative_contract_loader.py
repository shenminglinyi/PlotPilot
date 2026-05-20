"""叙事契约统一读取：Bible + worldbuilding 表合并后与正文/生成共用。"""
from __future__ import annotations

from typing import Any, Optional

from application.world.worldbuilding_merge import (
    bible_dto_world_settings_to_slices,
    merge_worldbuilding_table_and_bible_slices,
    worldbuilding_entity_to_slices,
)
from application.world.services.narrative_contract_text import build_narrative_contract_block
from domain.worldbuilding.worldbuilding import Worldbuilding


def load_merged_worldbuilding_slices(
    *,
    bible: Optional[Any] = None,
    worldbuilding: Optional[Worldbuilding] = None,
) -> dict:
    """与 AutoBibleGenerator._load_worldbuilding 相同合并策略。"""
    table_slices = worldbuilding_entity_to_slices(worldbuilding)
    bible_slices = bible_dto_world_settings_to_slices(bible)
    return merge_worldbuilding_table_and_bible_slices(table_slices, bible_slices)


def build_narrative_contract_for_sources(
    *,
    bible: Optional[Any] = None,
    worldbuilding: Optional[Worldbuilding] = None,
) -> str:
    slices = load_merged_worldbuilding_slices(bible=bible, worldbuilding=worldbuilding)
    return build_narrative_contract_block(
        bible=bible,
        worldbuilding=worldbuilding,
        worldbuilding_slices=slices,
    )


def build_narrative_contract_for_novel(
    novel_id: str,
    *,
    bible_repository: Any = None,
    worldbuilding_repository: Any = None,
) -> str:
    bible = None
    wb = None
    if bible_repository:
        try:
            from domain.novel.value_objects.novel_id import NovelId

            bible = bible_repository.get_by_novel_id(NovelId(novel_id))
        except Exception:
            bible = None
    if worldbuilding_repository:
        try:
            wb = worldbuilding_repository.get_by_novel_id(novel_id)
        except Exception:
            wb = None
    return build_narrative_contract_for_sources(bible=bible, worldbuilding=wb)
