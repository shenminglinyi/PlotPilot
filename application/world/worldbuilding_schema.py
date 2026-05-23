"""世界观五维 schema（单一数据源）与 LLM 自创字段 → 规范字段映射。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Mapping

from application.world.services.worldbuilding_field_text import worldbuilding_value_to_prose
from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS

# 与 AutoBibleGenerator / CPMS fields_desc 一致
WORLDBUILDING_DIMENSION_DEFS: Dict[str, Dict[str, Any]] = {
    "core_rules": {
        "label": "核心法则",
        "fields": {
            "power_system": "力量体系/科技树的描述",
            "physics_rules": "物理规律的特殊之处",
            "magic_tech": "魔法或科技的运作机制",
            "cost_and_limitation": "力量使用的代价与限制（修炼消耗、越级代价、禁忌代价）",
            "resource_scarcity": "稀缺资源及其分配（硬通货、垄断情况）",
        },
    },
    "geography": {
        "label": "地理生态",
        "fields": {
            "terrain": "主要地形特征",
            "climate": "气候特点与环境",
            "resources": "自然资源分布",
            "ecology": "生态系统与生物链",
            "forbidden_zones": "禁区/危险区域",
            "urban_core": "核心城市/聚居地",
            "hidden_realms": "秘境/隐藏空间",
        },
    },
    "society": {
        "label": "社会结构",
        "fields": {
            "politics": "政治体制与权力架构",
            "economy": "经济模式与贸易",
            "class_system": "阶级/等级系统",
            "power_structure": "明暗权力结构（明面与暗面的统治体系）",
            "oppression_mechanism": "压迫/控制机制（强者如何压制弱者）",
            "class_division": "阶层划分与流动壁垒",
        },
    },
    "culture": {
        "label": "历史文化",
        "fields": {
            "history": "关键历史事件与时代背景",
            "religion": "宗教信仰体系",
            "taboos": "文化禁忌与违逆后果",
            "worship": "崇拜对象与祭祀仪式",
            "oaths_and_curses": "誓言体系与诅咒",
        },
    },
    "daily_life": {
        "label": "沉浸感细节",
        "fields": {
            "food_clothing": "衣食住行的日常细节",
            "language_slang": "俚语、口音与方言",
            "entertainment": "娱乐方式与消遣",
            "survival_tactics": "底层/弱者的生存策略",
            "market_reality": "市场/交易的真实状况",
            "food_and_drink": "饮食文化与特色食物",
            "slang_and_profanity": "粗话、黑话与市井语言",
        },
    },
}

# LLM 常见自创键 → 规范字段（按维度）
DIMENSION_FIELD_ALIASES: Dict[str, Dict[str, str]] = {
    "core_rules": {
        "name": "power_system",
        "essence": "power_system",
        "power_system": "power_system",
        "physics": "physics_rules",
        "physics_rules": "physics_rules",
        "magic": "magic_tech",
        "magic_tech": "magic_tech",
        "technology": "magic_tech",
        "core_cost": "cost_and_limitation",
        "cost": "cost_and_limitation",
        "cost_and_limitation": "cost_and_limitation",
        "limitation": "cost_and_limitation",
        "limit": "cost_and_limitation",
        "resource": "resource_scarcity",
        "resource_scarcity": "resource_scarcity",
        "scarcity": "resource_scarcity",
        "fatal_flaw": "cost_and_limitation",
        "realm_structure": "power_system",
    },
    "geography": {
        "continent_name": "terrain",
        "key_regions": "terrain",
        "terrain": "terrain",
        "climate_impact": "climate",
        "climate": "climate",
        "resources": "resources",
        "ecology": "ecology",
        "forbidden_zones": "forbidden_zones",
        "urban_core": "urban_core",
        "hidden_realms": "hidden_realms",
        "realm_structure": "hidden_realms",
        "survival_rule": "ecology",
    },
    "society": {
        "ruling_class": "power_structure",
        "middle_class": "class_division",
        "lower_class": "class_division",
        "power_structure": "power_structure",
        "oppression": "oppression_mechanism",
        "oppression_mechanism": "oppression_mechanism",
        "class_division": "class_division",
        "politics": "politics",
        "economy": "economy",
        "class_system": "class_system",
        "currency": "economy",
        "black_market": "economy",
        "slave_trade": "economy",
    },
    "culture": {
        "dominant_faith": "religion",
        "doctrine": "religion",
        "truth": "religion",
        "rituals": "worship",
        "religion": "religion",
        "history": "history",
        "taboos": "taboos",
        "worship": "worship",
        "values": "taboos",
        "art_and_literature": "history",
        "punishment": "taboos",
        "禁忌": "taboos",
    },
    "daily_life": {
        "food_clothing": "food_clothing",
        "food_and_drink": "food_and_drink",
        "language_slang": "language_slang",
        "slang_and_profanity": "slang_and_profanity",
        "entertainment": "entertainment",
        "survival_tactics": "survival_tactics",
        "market_reality": "market_reality",
    },
}

# 无法识别时落入该维度的「主字段」
_DIMENSION_OVERFLOW_FIELD: Dict[str, str] = {
    "core_rules": "power_system",
    "geography": "terrain",
    "society": "politics",
    "culture": "history",
    "daily_life": "food_clothing",
}

# 子串启发（小写匹配 raw_key）
_KEYWORD_HINTS: Dict[str, tuple[tuple[str, str], ...]] = {
    "core_rules": (
        ("cost", "cost_and_limitation"),
        ("limit", "cost_and_limitation"),
        ("代价", "cost_and_limitation"),
        ("resource", "resource_scarcity"),
        ("稀缺", "resource_scarcity"),
        ("physics", "physics_rules"),
        ("物理", "physics_rules"),
        ("magic", "magic_tech"),
        ("tech", "magic_tech"),
    ),
    "geography": (
        ("climate", "climate"),
        ("气候", "climate"),
        ("region", "terrain"),
        ("terrain", "terrain"),
        ("ecology", "ecology"),
        ("生态", "ecology"),
    ),
    "society": (
        ("econom", "economy"),
        ("class", "class_system"),
        ("politic", "politics"),
        ("oppress", "oppression_mechanism"),
    ),
    "culture": (
        ("relig", "religion"),
        ("taboo", "taboos"),
        ("禁忌", "taboos"),
        ("worship", "worship"),
        ("history", "history"),
    ),
    "daily_life": (
        ("food", "food_clothing"),
        ("slang", "language_slang"),
        ("market", "market_reality"),
        ("survival", "survival_tactics"),
    ),
}


def schema_field_keys(dim_key: str) -> frozenset[str]:
    dim = WORLDBUILDING_DIMENSION_DEFS.get(dim_key, {})
    fields = dim.get("fields") or {}
    return frozenset(fields.keys())


def resolve_canonical_field(dim_key: str, raw_key: str) -> str:
    """将 LLM 输出的字段名映射到 schema 规范键。"""
    key = str(raw_key).strip()
    if not key:
        return _DIMENSION_OVERFLOW_FIELD.get(dim_key, key)

    aliases = DIMENSION_FIELD_ALIASES.get(dim_key, {})
    if key in aliases:
        return aliases[key]

    canonical = schema_field_keys(dim_key)
    if key in canonical:
        return key

    low = key.lower()
    for hint, target in _KEYWORD_HINTS.get(dim_key, ()):
        if hint in low:
            return target

    return _DIMENSION_OVERFLOW_FIELD.get(dim_key, key)


def canonicalize_dimension_fields(
    dim_key: str,
    raw: Mapping[str, Any],
) -> Dict[str, str]:
    """维度 dict → 仅含规范字段键的中文段落；自创键合并进对应规范槽位。"""
    buckets: Dict[str, list[str]] = defaultdict(list)

    for raw_k, raw_v in raw.items():
        prose = worldbuilding_value_to_prose(raw_v)
        if not prose:
            continue
        target = resolve_canonical_field(dim_key, str(raw_k))
        if target in buckets and prose in buckets[target]:
            continue
        buckets[target].append(prose)

    return {k: "\n\n".join(parts) for k, parts in buckets.items() if parts}


def build_fields_desc_for_prompt() -> str:
    """CPMS user.md 的 {fields_desc} 占位内容。"""
    lines: list[str] = []
    for dim_key in WORLD_BUILDING_DIMENSION_KEYS:
        dim_def = WORLDBUILDING_DIMENSION_DEFS[dim_key]
        lines.append(f'    "{dim_key}": {{')
        fields = list(dim_def["fields"].items())
        for idx, (fk, desc) in enumerate(fields):
            comma = "," if idx < len(fields) - 1 else ""
            lines.append(
                f'      "{fk}": "（{desc}。在此写一段中文正文，不少于80字；勿嵌套JSON或英文键）"{comma}'
            )
        dim_comma = "," if dim_key != WORLD_BUILDING_DIMENSION_KEYS[-1] else ""
        lines.append(f"    }}{dim_comma}")
    return "\n".join(lines)
