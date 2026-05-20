"""通用：从 LLM token 流中增量提取 JSON 对象与字符串字段。

不依赖具体业务 schema；世界观 / 人物数组等上层解析器复用本模块。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

_STRING_KV_RE = re.compile(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
_STREAMING_TAIL_RE = re.compile(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:\s*"((?:[^"\\]|\\.)*)$')


def _unescape_json_string(s: str) -> str:
    return s.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


@dataclass
class JsonStreamBuffer:
    """累积流式文本。"""

    text: str = ""

    def feed(self, chunk: str) -> None:
        if chunk:
            self.text += chunk


def find_key_object_brace_start(buf: str, key: str) -> Optional[int]:
    """定位 ``"key": {`` 中起始 ``{`` 的下标。"""
    pattern = rf'"{re.escape(key)}"\s*:\s*\{{'
    m = re.search(pattern, buf)
    if not m:
        return None
    return m.end() - 1


def scan_balanced_brace_end(buf: str, brace_start: int) -> Optional[int]:
    """从 ``brace_start`` 的 ``{`` 扫描到匹配的 ``}``，返回闭合 ``}`` 的下标 +1；未完成则 None。"""
    if brace_start < 0 or brace_start >= len(buf) or buf[brace_start] != "{":
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(brace_start, len(buf)):
        ch = buf[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def try_parse_json_object(buf: str, brace_start: int) -> Optional[Tuple[dict, int]]:
    """对象闭合后 ``json.loads``，返回 (dict, end_exclusive)。"""
    end = scan_balanced_brace_end(buf, brace_start)
    if end is None:
        return None
    try:
        parsed = json.loads(buf[brace_start:end])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed, end


def extract_complete_string_fields(object_body: str) -> Dict[str, str]:
    """从未闭合的对象片段中提取已写完的 ``"key": "value"`` 字符串对。"""
    out: Dict[str, str] = {}
    for m in _STRING_KV_RE.finditer(object_body):
        out[m.group(1)] = _unescape_json_string(m.group(2))
    return out


def extract_streaming_tail_string_field(object_body: str) -> Optional[Tuple[str, str]]:
    """提取末尾正在书写、尚未闭合引号的字段 (key, partial_value)。"""
    sm = _STREAMING_TAIL_RE.search(object_body)
    if not sm:
        return None
    key = sm.group(1)
    if key in extract_complete_string_fields(object_body):
        return None
    return key, _unescape_json_string(sm.group(2))
