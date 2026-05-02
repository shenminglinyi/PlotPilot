from application.ai.llm_json_extract import parse_llm_json_to_dict, strip_json_fences


def test_strip_json_fences():
    raw = '前缀\n```json\n{"a": 1}\n```\n后缀'
    assert strip_json_fences(raw).strip() == '{"a": 1}'


def test_parse_llm_json_to_dict_with_junk():
    raw = 'x ```\n{"k": "v"}\n``` y'
    data, errs = parse_llm_json_to_dict(raw)
    assert errs == []
    assert data == {"k": "v"}


def test_parse_llm_json_to_dict_repairs_unclosed_string():
    raw = '{"chapter_contract": {"chapter_question": "灰卡为什么能刷开门禁？'
    data, errs = parse_llm_json_to_dict(raw)
    assert errs == []
    assert data["chapter_contract"]["chapter_question"].startswith("灰卡")
