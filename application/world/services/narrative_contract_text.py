"""叙事契约文本：向导与 Bible 中「长期约束」的统一格式化。

供 ContextBudgetAllocator、DAG ctx_blueprint 等复用，避免各处重复拼接。"""
from __future__ import annotations

from typing import Dict, List, Optional

from domain.bible.entities.bible import Bible
from domain.worldbuilding.worldbuilding import Worldbuilding


# 与前端向导 WB_DIMS / domain Worldbuilding 字段一致
_WB_SECTIONS: List[tuple[str, List[tuple[str, str]]]] = [
    (
        "核心法则与底层逻辑",
        [
            ("力量体系/科技树", "power_system"),
            ("物理规律", "physics_rules"),
            ("魔法/科技机制", "magic_tech"),
        ],
    ),
    (
        "地理与生态",
        [
            ("地形", "terrain"),
            ("气候", "climate"),
            ("资源", "resources"),
            ("生态链", "ecology"),
        ],
    ),
    (
        "社会与权力",
        [
            ("政治体制", "politics"),
            ("经济模式", "economy"),
            ("阶级结构", "class_system"),
        ],
    ),
    (
        "历史、信仰与文化",
        [
            ("关键历史", "history"),
            ("宗教信仰", "religion"),
            ("文化禁忌", "taboos"),
        ],
    ),
    (
        "日常生活与沉浸细节",
        [
            ("衣食住行", "food_clothing"),
            ("语言/俚语", "language_slang"),
            ("娱乐方式", "entertainment"),
        ],
    ),
]


def format_worldbuilding_for_prompt(wb: Optional[Worldbuilding]) -> str:
    """将 worldbuilding 表实体转为紧凑正文（仅非空字段）。"""
    if wb is None:
        return ""

    lines: List[str] = ["【世界观五维（作者确认）】"]
    empty = True
    for title, fields in _WB_SECTIONS:
        block: List[str] = []
        for label, attr in fields:
            val = (getattr(wb, attr, None) or "").strip()
            if val:
                block.append(f"- {label}：{val}")
        if block:
            lines.append(f"▸ {title}")
            lines.extend(block)
            empty = False

    if empty:
        return ""
    return "\n".join(lines)


def format_style_notes_for_prompt(bible: Optional[Bible]) -> str:
    """Bible 文风/惯例类 style_notes。"""
    if bible is None:
        return ""
    notes = getattr(bible, "style_notes", None) or []
    if not notes:
        return ""

    lines: List[str] = ["【文风与叙述公约】"]
    for sn in notes:
        cat = (getattr(sn, "category", None) or "").strip()
        content = (getattr(sn, "content", None) or "").strip()
        if not content:
            continue
        if cat:
            lines.append(f"- [{cat}] {content}")
        else:
            lines.append(f"- {content}")

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def format_world_setting_rules_for_prompt(bible: Optional[Bible]) -> str:
    """Bible 中 setting_type=rule 的条目（补充五维表之外的硬规则）。"""
    if bible is None:
        return ""
    settings = getattr(bible, "world_settings", None) or []
    rules = [s for s in settings if getattr(s, "setting_type", "") == "rule"]
    if not rules:
        return ""

    lines: List[str] = ["【世界规则条目（Bible）】"]
    for s in rules:
        name = (getattr(s, "name", None) or "").strip()
        desc = (getattr(s, "description", None) or "").strip()
        if not name and not desc:
            continue
        if name and desc:
            lines.append(f"- {name}：{desc}")
        elif name:
            lines.append(f"- {name}")
        else:
            lines.append(f"- {desc}")

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def build_narrative_contract_block(
    *,
    bible: Optional[Bible],
    worldbuilding: Optional[Worldbuilding],
) -> str:
    """合并：文风公约 → 五维世界观 → Bible 规则条目。空段自动省略。"""
    parts: List[str] = []
    style = format_style_notes_for_prompt(bible)
    if style:
        parts.append(style)
    wb_text = format_worldbuilding_for_prompt(worldbuilding)
    if wb_text:
        parts.append(wb_text)
    rules = format_world_setting_rules_for_prompt(bible)
    if rules:
        parts.append(rules)

    if not parts:
        return ""
    return "\n\n".join(parts)


def build_ctx_blueprint_outputs(
    *,
    bible: Optional[Bible],
    worldbuilding: Optional[Worldbuilding],
) -> Dict[str, str]:
    """ctx_blueprint 节点三路输出：规则摘要 / 禁忌 / 氛围感。"""
    world_rules = ""
    if bible:
        world_rules = format_world_setting_rules_for_prompt(bible)
    wb_for_rules = format_worldbuilding_for_prompt(worldbuilding)
    if wb_for_rules:
        world_rules = f"{wb_for_rules}\n\n{world_rules}".strip() if world_rules else wb_for_rules

    taboos = ""
    if worldbuilding is not None:
        t = (worldbuilding.taboos or "").strip()
        if t:
            taboos = f"【文化禁忌】\n{t}"

    atmosphere = format_style_notes_for_prompt(bible)

    return {
        "world_rules": world_rules,
        "taboos": taboos,
        "atmosphere": atmosphere,
    }
