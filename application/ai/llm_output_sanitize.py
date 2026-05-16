"""从模型输出中剥离不应展示给用户的推理/思维链片段。

部分「thinking」或带 reasoning 通道的模型会把链式思考混在正文中；结构化 JSON 管线
已有部分清洗，小说正文生成路径此前未统一处理，导致用户可见正文被污染。

🔥 覆盖的模型及变体：
- DeepSeek-R1: <redacted_reasoning>...</redacted_reasoning>
- DeepSeek-R1: <think>...</think> (可能带 | 变体 <think|>)
- DeepSeek-V3: <thinking>...</thinking>
- QwQ:
- Gemini thinking: <thinking>...</thinking>
- 部分模型: [thinking]...[/thinking]
- 🔥 新增：DeepSeek 聊天模型偶尔在正文前添加「我来分析一下...」等前言
- 🔥 新增：某些模型输出 <!-- reason -->...<!-- /reason --> XML 注释
- 🔥 新增：某些模型输出 **thinking**... 等 Markdown 格式思考链
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
# 🔥 新增：XML 注释形式 <!-- reason -->...<!-- /reason -->
_REASON_COMMENT = re.compile(
    r"<!--\s*reason\s*-->.*?<!--\s*/reason\s*-->",
    re.DOTALL | re.IGNORECASE,
)
# 🔥 新增：Markdown 加粗思考 **thinking**...\*\*end thinking\*\*
_MD_THINKING = re.compile(
    r"\*\*thinking\*\*.*?\*\*end\s+thinking\*\*",
    re.DOTALL | re.IGNORECASE,
)
# 🔥 新增：部分模型在正文前加「分析：...」或「Analysis: ...」后跟换行
#          但这太容易误匹配，只处理明确以换行结束的前言
_PREFACE_ANALYSIS = re.compile(
    r"^(?:我来分析一下|分析[：:]|Analysis[：:]).*?\n(?=[^\n])",
    re.DOTALL | re.IGNORECASE,
)


def strip_reasoning_artifacts(raw: str) -> str:
    """移除常见推理块标签与围栏，保留其余文本顺序不变。

    覆盖：DeepSeek/Qwen 系 redacted_reasoning、think/thinking 标签及方括号变体，
    以及 XML 注释、Markdown 格式等变体。
    """
    if not raw:
        return ""

    s = raw
    s = _REDACTED_BLOCK.sub("", s)
    s = _THINK_BLOCK.sub("", s)
    s = _THINKING_BLOCK.sub("", s)
    s = _BRACKET_THINKING.sub("", s)
    s = _REASON_COMMENT.sub("", s)
    s = _MD_THINKING.sub("", s)
    s = _PREFACE_ANALYSIS.sub("", s)
    return s
