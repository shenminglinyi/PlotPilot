"""检测 Chat Completions 原始输出中是否仍含常见「思考」围栏（集成测试 / 自检）。"""

from __future__ import annotations

from typing import Any, Optional


def bundle_message_text_fields(
    content: Optional[str],
    reasoning: Optional[str] = None,
    reasoning_content: Optional[str] = None,
) -> str:
    """拼接可能被服务端拆到多字段的文本，用于检测。"""
    parts = [content or "", reasoning or "", reasoning_content or ""]
    return "".join(parts)


def raw_text_contains_think_markers(text: str) -> bool:
    """若正文仍含常见 think / redacted 标记则返回 True。"""
    if not text:
        return False
    low = text.lower()
    needles = (
        "\x3cthink\x3e",
        "\x3c\x3cthink\x3e\x3e",
        "<think>",
    )
    return any(n in low for n in needles)


def message_dump_has_think_leak(message: Any) -> bool:
    """对 OpenAI SDK 的 message 对象做 model_dump 后检测常见思考字段。"""
    try:
        data = message.model_dump(mode="python", exclude_none=False)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    bundle = bundle_message_text_fields(
        data.get("content") if isinstance(data.get("content"), str) else None,
        data.get("reasoning") if isinstance(data.get("reasoning"), str) else None,
        data.get("reasoning_content") if isinstance(data.get("reasoning_content"), str) else None,
    )
    if raw_text_contains_think_markers(bundle):
        return True
    # 多模态 content 列表
    raw_c = data.get("content")
    if isinstance(raw_c, list):
        for block in raw_c:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str) and raw_text_contains_think_markers(t):
                    return True
    return False


def reasoning_channel_should_be_empty_when_disabled(message: Any) -> Optional[str]:
    """若 message.reasoning / reasoning_content 非空则返回说明字符串，否则 None。"""
    r = getattr(message, "reasoning", None)
    rc = getattr(message, "reasoning_content", None)
    if isinstance(r, str) and r.strip():
        return "message.reasoning 非空（关思考时期望为空）"
    if isinstance(rc, str) and rc.strip():
        return "message.reasoning_content 非空（关思考时期望为空）"
    return None
