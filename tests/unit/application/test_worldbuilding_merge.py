"""世界观合并逻辑：Bible 扩展字段与世界映射表对齐。"""
from domain.worldbuilding.worldbuilding import Worldbuilding

from application.world.dtos.bible_dto import BibleDTO, WorldSettingDTO
from application.world.worldbuilding_merge import (
    bible_dto_world_settings_to_slices,
    merge_worldbuilding_table_and_bible_slices,
    project_slices_to_legacy_api_shape,
    worldbuilding_entity_to_slices,
    worldbuilding_slices_nonempty,
)


def test_merge_keeps_llm_extra_and_table_overwrites():
    bible_sl = {"core_rules": {"power_system": "B", "cost_and_limitation": "EXTRA"}}
    table_sl = worldbuilding_entity_to_slices(
        Worldbuilding(
            id="wb-1",
            novel_id="n1",
            power_system="A",
            physics_rules="P",
            magic_tech="",
        )
    )
    merged = merge_worldbuilding_table_and_bible_slices(table_sl, bible_sl)
    cr = merged["core_rules"]
    assert cr["power_system"] == "A"
    assert cr["cost_and_limitation"] == "EXTRA"
    assert cr["physics_rules"] == "P"


def test_projection_appends_extra_to_tail_field():
    full = {"core_rules": {"power_system": "X", "cost_and_limitation": "尾段"}}
    legacy = project_slices_to_legacy_api_shape(full)
    assert "尾段" in legacy["core_rules"]["magic_tech"]
    assert legacy["core_rules"]["power_system"] == "X"


def test_projection_omits_empty_legacy_fields():
    legacy = project_slices_to_legacy_api_shape({})
    assert legacy == {
        "core_rules": {},
        "geography": {},
        "society": {},
        "culture": {},
        "daily_life": {},
    }


def test_slices_nonempty_detects_nested():
    assert not worldbuilding_slices_nonempty(None)
    assert not worldbuilding_slices_nonempty({"core_rules": {}})
    assert worldbuilding_slices_nonempty({"culture": {"history": "h"}})


def test_bible_dto_slices_parses_dot_names():
    dto = BibleDTO(
        id="b",
        novel_id="n",
        characters=[],
        world_settings=[
            WorldSettingDTO(
                id="1",
                name="society.politics",
                description="王权",
                setting_type="rule",
            ),
        ],
        locations=[],
        timeline_notes=[],
        style_notes=[],
    )
    sl = bible_dto_world_settings_to_slices(dto)
    assert sl["society"]["politics"] == "王权"
