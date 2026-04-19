"""从模型输出中剥离不应展示给用户的推理/思维链片段。

部分「thinking」或带 reasoning 通道的模型会把链式思考混在正文中；结构化 JSON 管线
已有部分清洗，小说正文生成路径此前未统一处理，导致用户可见正文被污染。
"""
from __future__ import annotations

import re

# 使用 \\x3c / \\x3e 表示尖括号，避免部分工具链误解析 XML 状字面量。
_REDACTED_BLOCK = re.compile(
    br"\x3credacted_reasoning\x3e.*?\x3c/redacted_reasoning\x3e".decode(),
    re.DOTALL,
)
_THINK_BLOCK = re.compile(
    br"\x3cthink\x7c?\x3e.*?\x3c\x2fthink\x7c?\x3e".decode(),
    re.DOTALL,
)
_THINKING_BLOCK = re.compile(
    br"\x3cthinking\x3e.*?\x3c\x2fthinking\x3e".decode(),
    re.DOTALL,
)
_BRACKET_THINKING = re.compile(
    r"\[thinking\].*?\[/thinking\]",
    re.DOTALL | re.IGNORECASE,
)


def strip_reasoning_artifacts(raw: str) -> str:
    """移除常见推理块标签与围栏，保留其余文本顺序不变。

    覆盖：DeepSeek/Qwen 系 redacted_reasoning、think/thinking 标签及方括号变体。
    """
    if not raw:
        return ""

    s = raw
    s = _REDACTED_BLOCK.sub("", s)
    s = _THINK_BLOCK.sub("", s)
    s = _THINKING_BLOCK.sub("", s)
    s = _BRACKET_THINKING.sub("", s)
    return s
