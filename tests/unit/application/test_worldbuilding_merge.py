"""世界观合并逻辑：按 Plotpilot_writer 基础字段对齐。"""
from domain.worldbuilding.worldbuilding import Worldbuilding

from application.world.dtos.bible_dto import BibleDTO, WorldSettingDTO
from application.world.worldbuilding_merge import (
    bible_dto_world_settings_to_slices,
    merge_worldbuilding_table_and_bible_slices,
    project_slices_to_contract_api_shape,
    worldbuilding_entity_to_slices,
    worldbuilding_slices_nonempty,
)
from application.world.services.narrative_contract_loader import load_merged_worldbuilding_slices


def test_merge_filters_extra_and_table_overwrites():
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
    assert "cost_and_limitation" not in cr
    assert cr["physics_rules"] == "P"


def test_projection_drops_extra_fields():
    full = {"core_rules": {"power_system": "X", "cost_and_limitation": "尾段"}}
    projected = project_slices_to_contract_api_shape(full)
    assert "cost_and_limitation" not in projected["core_rules"]
    assert projected["core_rules"]["power_system"] == "X"


def test_projection_omits_empty_contract_fields():
    projected = project_slices_to_contract_api_shape({})
    assert projected == {
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


def test_bible_dto_slices_filters_extra_dot_names():
    dto = BibleDTO(
        id="b",
        novel_id="n",
        characters=[],
        world_settings=[
            WorldSettingDTO(
                id="1",
                name="core_rules.cost_and_limitation",
                description="旧扩展字段",
                setting_type="rule",
            ),
        ],
        locations=[],
        timeline_notes=[],
        style_notes=[],
    )
    sl = bible_dto_world_settings_to_slices(dto)
    assert "cost_and_limitation" not in sl["core_rules"]


def test_v2_worldbuilding_dimensions_are_single_source_of_truth():
    dto = BibleDTO(
        id="b",
        novel_id="n",
        characters=[],
        world_settings=[
            WorldSettingDTO(
                id="1",
                name="core_rules.power_system",
                description="旧 Bible 世界观不应覆盖 V2",
                setting_type="rule",
            ),
        ],
        locations=[],
        timeline_notes=[],
        style_notes=[],
    )
    wb = Worldbuilding(
        id="wb-1",
        novel_id="n",
        schema_version=2,
        dimensions={
            "core_rules": {
                "power_system": "V2 世界观",
                "cost_and_limitation": "V2 代价",
            }
        },
    )

    merged = load_merged_worldbuilding_slices(bible=dto, worldbuilding=wb)

    assert merged["core_rules"]["power_system"] == "V2 世界观"
    assert "cost_and_limitation" not in merged["core_rules"]
    assert "旧 Bible" not in merged["core_rules"]["power_system"]
