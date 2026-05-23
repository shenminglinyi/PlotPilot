"""世界观单次流式增量解析器测试"""
import json

from application.world.services.worldbuilding_stream_parser import (
    WorldbuildingStreamIncrementalParser,
    _try_extract_dimension_object,
)


def test_try_extract_dimension_object_finds_complete_block():
    buf = json.dumps(
        {
            "worldbuilding": {
                "core_rules": {
                    "power_system": "灵气复苏后的异能体系",
                    "physics_rules": "常态物理",
                },
                "geography": {
                    "terrain": "多山",
                },
            }
        },
        ensure_ascii=False,
    )
    got = _try_extract_dimension_object(buf, "core_rules")
    assert got is not None
    fields, _, _ = got
    assert "灵气" in fields["power_system"]


def test_incremental_parser_emits_dimensions_in_order():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"core_rules": {"power_system": "A", "physics_rules": "B", "magic_tech": "C"}, '
    part2 = '"geography": {"terrain": "山"}}}'
    events = []
    events.extend(parser.feed(part1))
    events.extend(parser.feed(part2))
    keys = [e["key"] for e in events if e["type"] == "dimension"]
    assert "core_rules" in keys
    assert "geography" in keys


def test_parser_canonicalizes_llm_alias_keys_and_emits_field_events():
    parser = WorldbuildingStreamIncrementalParser()
    chunk = (
        '{"worldbuilding": {"core_rules": {'
        '"name": "劫力体系", '
        '"essence": "吸收劫气修炼", '
        '"core_cost": "渡劫代价"'
        "}}}"
    )
    events = parser.feed(chunk)
    fields = [e for e in events if e["type"] == "field"]
    field_names = {e["field"] for e in fields}
    assert "power_system" in field_names
    assert "cost_and_limitation" in field_names
    assert "name" not in field_names
    dim = next(e for e in events if e["type"] == "dimension")
    assert "name" not in dim["content"]
    assert "劫力" in dim["content"]["power_system"]


def test_parser_emits_field_partial_while_streaming():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"core_rules": {"name": "劫力'
    part2 = '体系"}}}'
    events = []
    events.extend(parser.feed(part1))
    partials = [e for e in events if e["type"] == "field_partial"]
    assert partials
    assert partials[-1]["field"] == "power_system"
    assert "劫力" in partials[-1]["value"]
    events.extend(parser.feed(part2))
    assert any(e["type"] == "dimension" for e in events)


def test_parser_maps_invalid_dimension_string_to_primary_field():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"society": "剑修贵族垄断灵石矿'
    part2 = '，非剑修宗门需上缴七成收益才能获得庇护"}}'
    events = []
    events.extend(parser.feed(part1))
    partials = [e for e in events if e["type"] == "field_partial"]
    assert partials
    assert partials[-1]["key"] == "society"
    assert partials[-1]["field"] == "politics"
    events.extend(parser.feed(part2))
    fields = [e for e in events if e["type"] == "field"]
    assert any(e["key"] == "society" and e["field"] == "politics" for e in fields)
