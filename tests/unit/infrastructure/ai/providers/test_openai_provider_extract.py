"""OpenAIProvider 响应解析（reasoning 字段兼容）

本文件是**单元测试**：用 ``monkeypatch`` 读写 ``os.environ``，模拟你在 shell / 系统里
配好的环境变量；**不会**去加载项目根目录的 ``.env``（pytest 默认也不加载）。

这样做的原因：
- CI / 其他机器上没有你的 ``.env``，测试仍须可重复通过；
- 只测「给定环境变量组合时，函数返回值是否符合预期」，与运行时 ``os.getenv`` 行为一致。

实机校验见 ``tests/integration/infrastructure/ai/test_qwen_openai_compat_no_think_live.py``
（需 ``RUN_QWEN_NO_THINK_LIVE=1`` 与根目录 ``.env``，与 ``.env.example`` 中 Qwen3.5 一节一致）。
"""
from openai.types.chat.chat_completion_chunk import ChoiceDelta
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from infrastructure.ai.providers.openai_provider import (
    _extract_chat_message_text,
    _extract_stream_delta_text,
    _maybe_strip_for_no_think,
    _openai_no_think_request_options,
)


def test_extract_prefers_content_over_reasoning():
    m = ChatCompletionMessage.model_validate(
        {"role": "assistant", "content": "visible", "reasoning": "hidden"}
    )
    assert _extract_chat_message_text(m) == "visible"


def test_extract_reasoning_when_content_empty():
    m = ChatCompletionMessage.model_validate(
        {"role": "assistant", "content": None, "reasoning": '{"world": true}'}
    )
    assert _extract_chat_message_text(m) == '{"world": true}'


def test_extract_stream_delta_reasoning():
    d = ChoiceDelta.model_validate({"content": None, "reasoning": "x"})
    assert _extract_stream_delta_text(d) == "x"


def test_extract_skips_reasoning_when_llm_disable_reasoning(monkeypatch):
    monkeypatch.setenv("LLM_DISABLE_REASONING", "true")
    m = ChatCompletionMessage.model_validate(
        {"role": "assistant", "content": None, "reasoning": "not-for-json"}
    )
    assert _extract_chat_message_text(m) == ""


def test_stream_delta_skips_reasoning_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_DISABLE_REASONING", "true")
    d = ChoiceDelta.model_validate({"content": None, "reasoning": "x"})
    assert _extract_stream_delta_text(d) is None


def test_openai_no_think_options_requires_base_url(monkeypatch):
    """验证 ``_openai_no_think_request_options`` 在 env + base_url 组合下的字典形状（不读 .env）。"""
    monkeypatch.delenv("LLM_DISABLE_REASONING", raising=False)
    monkeypatch.delenv("LLM_FORCE_COMPAT_NO_THINK_EXTRAS", raising=False)
    monkeypatch.delenv("LLM_QWEN_ASSISTANT_PREFILL", raising=False)
    assert _openai_no_think_request_options(None) == {}
    assert _openai_no_think_request_options("") == {}

    monkeypatch.setenv("LLM_DISABLE_REASONING", "1")
    assert _openai_no_think_request_options(None) == {}
    assert _openai_no_think_request_options("http://127.0.0.1:1234/v1") == {
        "extra_body": {
            "reasoning": "off",
            "chat_template_kwargs": {"enable_thinking": False},
            "continue_assistant_turn": True,
        }
    }


def test_openai_no_think_options_force_without_base_url(monkeypatch):
    monkeypatch.setenv("LLM_DISABLE_REASONING", "true")
    monkeypatch.setenv("LLM_FORCE_COMPAT_NO_THINK_EXTRAS", "1")
    monkeypatch.delenv("LLM_QWEN_ASSISTANT_PREFILL", raising=False)
    assert _openai_no_think_request_options(None) == {
        "extra_body": {
            "reasoning": "off",
            "chat_template_kwargs": {"enable_thinking": False},
            "continue_assistant_turn": True,
        }
    }


def test_maybe_strip_think_tags_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_DISABLE_REASONING", "true")
    raw = "\x3cthink\x3e...internal...\x3c/think\x3e\n{\"a\": 1}"
    assert _maybe_strip_for_no_think(raw) == '{"a": 1}'


def test_maybe_strip_redacted_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_DISABLE_REASONING", "true")
    raw = "<think>x</think>{\"b\": 2}"
    assert _maybe_strip_for_no_think(raw) == '{"b": 2}'


def test_openai_no_think_options_without_assistant_prefill(monkeypatch):
    monkeypatch.setenv("LLM_DISABLE_REASONING", "true")
    monkeypatch.setenv("LLM_QWEN_ASSISTANT_PREFILL", "false")
    body = _openai_no_think_request_options("http://localhost:1/v1")["extra_body"]
    assert "continue_assistant_turn" not in body
