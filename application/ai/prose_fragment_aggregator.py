"""落盘前的正文碎片化合并：单行换行的短叙事句连片为逗号贯通的长句。

设计目标：
- 尊重段落边界（空白行分隔的段落不跨段合并）。
- 遇对话行「…」或元信息【…】等保留换行分段。
- 遇超长行 (> short_line_max_chars) 视作独立节拍，不向其两侧短行「硬连」。"""
from __future__ import annotations

import re
from typing import List

_SHORT_DEFAULT = 52

# 对话 / OOC / 编辑器元信息起始：保留段内换行
_HARD_PREFIX = frozenset("「『【※")
_HARD_PREFIX_EXTENDED = frozenset(
    _HARD_PREFIX
    | frozenset(
        ('"', "'", "\u201c", "\u2018"),  # " ' “ ‘
    )
)


def aggregate_inline_prose_fragments(text: str, *, short_line_max_chars: int = _SHORT_DEFAULT) -> str:
    """将段落内相邻短行转为逗号连片；双换行段落结构不变。"""
    if not text or not str(text).strip():
        return text
    raw = str(text).replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"\n{2,}", raw)
    paras: List[str] = []
    for block in parts:
        merged = _merge_single_paragraph(block, short_line_max_chars).strip()
        if merged:
            paras.append(merged)
    out = "\n\n".join(paras)
    out = re.sub(r"，{2,}", "，", out)
    return out.rstrip()


def _is_hard_break_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    c0 = s[0]
    if c0 in _HARD_PREFIX_EXTENDED:
        return True
    if s.startswith("(\\") or s.startswith("(/"):
        return True
    return False


def _glue_segments(left: str, right: str) -> str:
    left = left.rstrip()
    right = right.lstrip()
    if not left:
        return right
    if not right:
        return left
    # 引号直接贴附（：「…」）
    if left[-1] in ":：" and right[0] in "「『\"\u201c\u2018'":
        return left + right
    if left[-1] in "，、；：（":
        return left + right
    if left[-1] in "。！？…":
        return left[:-1] + "，" + right
    return left + "，" + right


def _merge_single_paragraph(block: str, max_short: int) -> str:
    lines = [ln.strip() for ln in block.split("\n")]
    pieces: List[str] = []
    buf: List[str] = []

    def flush_buf() -> None:
        nonlocal buf
        if not buf:
            return
        if len(buf) == 1:
            pieces.append(buf[0])
        else:
            merged = buf[0]
            for ln in buf[1:]:
                merged = _glue_segments(merged, ln)
            pieces.append(merged)
        buf.clear()

    for line in lines:
        if not line:
            flush_buf()
            continue
        if _is_hard_break_line(line) or len(line) > max_short:
            flush_buf()
            pieces.append(line)
            continue
        buf.append(line)
    flush_buf()
    if not pieces:
        return ""
    if len(pieces) == 1:
        return pieces[0]
    return "\n".join(pieces)
