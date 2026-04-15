"""think_leak_detection 单元测试"""
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from infrastructure.ai.think_leak_detection import (
    message_dump_has_think_leak,
    raw_text_contains_think_markers,
    reasoning_channel_should_be_empty_when_disabled,
)


def test_raw_text_contains_think_markers():
    assert raw_text_contains_think_markers("prefix\x3cthink\x3ex\x3c/think\x3esuffix")
    assert raw_text_contains_think_markers("<think>x</think>")
    assert not raw_text_contains_think_markers('{"a":1}')


def test_message_dump_has_think_leak():
    m = ChatCompletionMessage.model_validate(
        {"role": "assistant", "content": "ok\x3cthink\x3eh\x3c/think\x3e"}
    )
    assert message_dump_has_think_leak(m)


def test_reasoning_channel_should_be_empty():
    m = ChatCompletionMessage.model_validate(
        {"role": "assistant", "content": "{}", "reasoning": "hidden"}
    )
    assert reasoning_channel_should_be_empty_when_disabled(m) is not None
