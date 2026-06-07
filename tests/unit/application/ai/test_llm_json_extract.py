from application.ai.llm_json_extract import parse_llm_json_to_any, parse_llm_json_to_dict, strip_json_fences


def test_strip_json_fences():
    raw = '前缀\n```json\n{"a": 1}\n```\n后缀'
    assert strip_json_fences(raw).strip() == '{"a": 1}'


def test_parse_llm_json_to_dict_with_junk():
    raw = 'x ```\n{"k": "v"}\n``` y'
    data, errs = parse_llm_json_to_dict(raw)
    assert errs == []
    assert data == {"k": "v"}


def test_parse_llm_json_to_any_accepts_array_root():
    raw = '前缀\n```json\n[{"name":"A"}]\n```\n后缀'
    data, errs = parse_llm_json_to_any(raw)
    assert errs == []
    assert data == [{"name": "A"}]


def test_parse_llm_json_to_any_recovers_truncated_characters_array():
    raw = (
        '{"characters":[{"name":"A","relationships":[]},'
        '{"name":"B","relationships":[]},'
        '{"name":"C","relationships":[{"target":"X","relation":"师徒"}'
    )
    data, errs = parse_llm_json_to_any(raw)
    assert errs == []
    assert isinstance(data, dict)
    assert [item["name"] for item in data["characters"]] == ["A", "B"]
