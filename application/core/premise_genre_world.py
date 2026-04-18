"""从 novels.premise 解析建档时写入的「类型 / 世界观基调」前缀（与前端 premisePresets 逻辑对齐）。"""
from __future__ import annotations

import re
from typing import Tuple


def parse_genre_world_from_premise(premise: str) -> Tuple[str, str]:
    """返回 (genre, world_preset)。无法解析时为空字符串。"""
    text = (premise or "").strip()
    if not text:
        return "", ""

    # 全篇搜索（不要求独占一行；兼容中英文分号）
    m = re.search(
        r"【类型：\s*([^】；]+?)\s*[；;]\s*世界观基调：\s*([^】]+?)\s*】",
        text,
        flags=re.DOTALL,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m2 = re.search(r"【类型：\s*([^】]+?)\s*】", text)
    if m2:
        return m2.group(1).strip(), ""

    # 无书名号：部分旧数据或截断
    m3 = re.search(
        r"类型：\s*([^\n；;]+?)\s*[；;]\s*世界观基调：\s*([^\n]+?)(?:\n|$)",
        text,
    )
    if m3:
        return m3.group(1).strip(), m3.group(2).strip()

    return "", ""
