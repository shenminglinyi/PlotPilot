"""通用 JSON 流增量提取器"""
from infrastructure.json_stream.incremental_extractor import (
    extract_complete_string_fields,
    extract_streaming_tail_string_field,
    find_key_object_brace_start,
    scan_balanced_brace_end,
)


def test_extract_complete_and_tail_string_fields():
    body = '"name": "劫力体系", "essence": "吸收劫气", "core_cost": "渡劫必'
    complete = extract_complete_string_fields(body)
    assert complete["name"] == "劫力体系"
    assert complete["essence"] == "吸收劫气"
    tail = extract_streaming_tail_string_field(body)
    assert tail == ("core_cost", "渡劫必")


def test_balanced_brace_detects_closed_object():
    buf = '{"core_rules": {"power_system": "A"}}'
    start = find_key_object_brace_start(buf, "core_rules")
    assert start is not None
    end = scan_balanced_brace_end(buf, start)
    assert end is not None
    assert buf[start:end] == '{"power_system": "A"}'
