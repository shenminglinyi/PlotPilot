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


def test_parser_ignores_non_contract_keys():
    parser = WorldbuildingStreamIncrementalParser()
    chunk = (
        '{"worldbuilding": {"core_rules": {'
        '"power_system": "劫力体系", '
        '"cost_and_limitation": "渡劫代价", '
        '"name": "自创字段"'
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


def test_parser_waits_for_closed_dimension_before_emitting_fields():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"core_rules": {"power_system": "劫力'
    part2 = '体系"}}}'
    events = []
    events.extend(parser.feed(part1))
    assert events == []
    events.extend(parser.feed(part2))
    assert any(e["type"] == "dimension" for e in events)


def test_parser_ignores_invalid_dimension_string():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"society": "剑修贵族垄断灵石矿'
    part2 = '，非剑修宗门需上缴七成收益才能获得庇护"}}'
    events = []
    events.extend(parser.feed(part1))
    assert events == []
    events.extend(parser.feed(part2))
    assert events == []


def test_parser_uses_closed_dimension_value_when_duplicate_keys_exist():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"culture": {"history": "选手", '
    part2 = '"history": "职业电竞联盟在十年前建立神经健康标准，但俱乐部用外包青训规避监管"}}}'

    events = []
    events.extend(parser.feed(part1))
    assert events == []

    events.extend(parser.feed(part2))
    history_fields = [
        e for e in events
        if e["type"] == "field" and e["key"] == "culture" and e["field"] == "history"
    ]
    assert history_fields[-1]["value"].startswith("职业电竞联盟")
    dim = next(e for e in events if e["type"] == "dimension" and e["key"] == "culture")
    assert dim["content"]["history"].startswith("职业电竞联盟")
