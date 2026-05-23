"""叙事契约文本：向导与 Bible 中「长期约束」的统一格式化。

供 ContextBudgetAllocator、DAG ctx_blueprint 等复用，避免各处重复拼接。"""
from __future__ import annotations

from typing import Dict, List, Optional

from domain.bible.entities.bible import Bible
from domain.worldbuilding.worldbuilding import Worldbuilding
from application.world.worldbuilding_merge import (
    WORLD_BUILDING_DIMENSION_KEYS,
    worldbuilding_slices_nonempty,
)
from application.world.worldbuilding_schema import WORLDBUILDING_DIMENSION_DEFS


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

_DIM_DISPLAY: Dict[str, str] = {
    "core_rules": "核心法则与底层逻辑",
    "geography": "地理与生态",
    "society": "社会与权力",
    "culture": "历史、信仰与文化",
    "daily_life": "日常生活与沉浸细节",
}

_FIELD_LABELS: Dict[str, str] = {}
for _title, _fields in _WB_SECTIONS:
    for _label, _attr in _fields:
        _FIELD_LABELS[_attr] = _label
for _dim in WORLDBUILDING_DIMENSION_DEFS.values():
    for _key, _label in (_dim.get("fields") or {}).items():
        _FIELD_LABELS.setdefault(_key, str(_label).split("（", 1)[0])


def format_worldbuilding_slices_for_prompt(
    slices: Optional[Dict[str, Dict[str, str]]],
) -> str:
    """合并后的五维 dict → 紧凑正文（含 SSE 扩展字段）。"""
    if not slices or not worldbuilding_slices_nonempty(slices):
        return ""

    lines: List[str] = ["【世界观五维（作者确认）】"]
    for dim in WORLD_BUILDING_DIMENSION_KEYS:
        blk = slices.get(dim) or {}
        items = [(k, str(v).strip()) for k, v in sorted(blk.items()) if str(v).strip()]
        if not items:
            continue
        lines.append(f"▸ {_DIM_DISPLAY.get(dim, dim)}")
        for key, val in items:
            label = _FIELD_LABELS.get(key, key.replace("_", " "))
            lines.append(f"- {label}：{val}")

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


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
    worldbuilding: Optional[Worldbuilding] = None,
    worldbuilding_slices: Optional[Dict[str, Dict[str, str]]] = None,
) -> str:
    """合并：文风公约 → 五维世界观 → Bible 规则条目。空段自动省略。"""
    parts: List[str] = []
    style = format_style_notes_for_prompt(bible)
    if style:
        parts.append(style)
    if worldbuilding_slices is not None:
        wb_text = format_worldbuilding_slices_for_prompt(worldbuilding_slices)
    else:
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
    worldbuilding: Optional[Worldbuilding] = None,
    worldbuilding_slices: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, str]:
    """ctx_blueprint 节点三路输出：规则摘要 / 禁忌 / 氛围感。"""
    if worldbuilding_slices is None and (bible is not None or worldbuilding is not None):
        from application.world.services.narrative_contract_loader import load_merged_worldbuilding_slices

        worldbuilding_slices = load_merged_worldbuilding_slices(
            bible=bible, worldbuilding=worldbuilding
        )

    world_rules = ""
    if bible:
        world_rules = format_world_setting_rules_for_prompt(bible)
    wb_for_rules = format_worldbuilding_slices_for_prompt(worldbuilding_slices)
    if not wb_for_rules:
        wb_for_rules = format_worldbuilding_for_prompt(worldbuilding)
    if wb_for_rules:
        world_rules = f"{wb_for_rules}\n\n{world_rules}".strip() if world_rules else wb_for_rules

    taboos = ""
    culture = (worldbuilding_slices or {}).get("culture") or {}
    t = (culture.get("taboos") or "").strip()
    if not t and worldbuilding is not None:
        t = (worldbuilding.taboos or "").strip()
    if t:
        taboos = f"【文化禁忌】\n{t}"

    atmosphere = format_style_notes_for_prompt(bible)

    return {
        "world_rules": world_rules,
        "taboos": taboos,
        "atmosphere": atmosphere,
    }
