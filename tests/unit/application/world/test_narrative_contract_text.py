"""narrative_contract_text 单元测试"""
from domain.bible.entities.bible import Bible
from domain.bible.entities.style_note import StyleNote
from domain.bible.entities.world_setting import WorldSetting
from domain.novel.value_objects.novel_id import NovelId
from domain.worldbuilding.worldbuilding import Worldbuilding

from application.world.services.narrative_contract_text import (
    build_ctx_blueprint_outputs,
    build_narrative_contract_block,
    format_worldbuilding_for_prompt,
)


def test_format_worldbuilding_skips_empty_sections():
    wb = Worldbuilding(id="wb1", novel_id="n1", power_system="  体系A  ")
    text = format_worldbuilding_for_prompt(wb)
    assert "体系A" in text
    assert "气候" not in text


def test_build_narrative_contract_block_orders_style_then_wb():
    bible = Bible("b1", NovelId("n1"))
    bible.add_style_note(StyleNote("s1", "文风公约", "冷峻克制"))
    wb = Worldbuilding(id="wb1", novel_id="n1", terrain="群山")
    block = build_narrative_contract_block(bible=bible, worldbuilding=wb)
    idx_style = block.index("文风")
    idx_wb = block.index("群山")
    assert idx_style < idx_wb


def test_format_worldbuilding_slices_filters_extension_fields():
    slices = {
        "core_rules": {
            "power_system": "体系",
            "cost_and_limitation": "越级反噬",
        },
    }
    from application.world.services.narrative_contract_text import (
        format_worldbuilding_slices_for_prompt,
    )

    text = format_worldbuilding_slices_for_prompt(slices)
    assert "越级反噬" not in text
    assert "cost_and_limitation" not in text
    assert "体系" in text


def test_build_ctx_blueprint_splits_taboos_and_atmosphere():
    bible = Bible("b1", NovelId("n1"))
    bible.add_style_note(StyleNote("s1", "氛围", "雨夜压抑"))
    bible.add_world_setting(WorldSetting("r1", "禁飞", "城内不得飞行", "rule"))
    wb = Worldbuilding(id="wb1", novel_id="n1", taboos="不可直视祭司")

    out = build_ctx_blueprint_outputs(bible=bible, worldbuilding=wb)
    assert "不可直视" in out["taboos"]
    assert "雨夜" in out["atmosphere"]
    assert "禁飞" in out["world_rules"]
