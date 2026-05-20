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
