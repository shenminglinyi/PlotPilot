"""strip_reasoning_artifacts 单元测试。"""
from application.ai.llm_output_sanitize import strip_reasoning_artifacts


def test_strip_redacted_reasoning_block():
    raw = (
        "<redacted_reasoning>内部推理</redacted_reasoning>"
        "第一章正文开始。"
    )
    assert strip_reasoning_artifacts(raw) == "第一章正文开始。"


def test_strip_think_tags():
    raw = "<think>step1</think>可见正文"
    assert strip_reasoning_artifacts(raw) == "可见正文"


def test_strip_think_tags_with_pipe():
    raw = "<think|>step1</think|>可见正文"
    assert strip_reasoning_artifacts(raw) == "可见正文"


def test_strip_thinking_tags():
    raw = "<thinking>plan</thinking>后文"
    assert strip_reasoning_artifacts(raw) == "后文"


def test_strip_bracket_thinking_case_insensitive():
    raw = "[thinking]x[/thinking]Y"
    assert strip_reasoning_artifacts(raw) == "Y"


def test_empty_and_no_tags():
    assert strip_reasoning_artifacts("") == ""
    assert strip_reasoning_artifacts("纯正文") == "纯正文"
