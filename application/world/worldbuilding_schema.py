"""世界观五维 schema（单一数据源）。"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Any, Dict, Mapping

from pydantic import ConfigDict, Field, ValidationError, create_model

from application.world.services.worldbuilding_field_text import worldbuilding_value_to_prose
from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS

MIN_WORLDBUILDING_FIELD_CHARS = 20
MAX_WORLDBUILDING_FIELD_CHARS = 500

# 与 AutoBibleGenerator / CPMS fields_desc 一致
WORLDBUILDING_DIMENSION_DEFS: Dict[str, Dict[str, Any]] = {
    "core_rules": {
        "label": "核心法则",
        "fields": {
            "power_system": "力量体系/科技树的描述",
            "physics_rules": "底层物理/时间/生理规律",
            "magic_tech": "技术接口与运作机制",
        },
    },
    "geography": {
        "label": "地理生态",
        "fields": {
            "terrain": "主要地形特征",
            "climate": "气候特点与环境",
            "resources": "自然资源分布",
            "ecology": "生态系统与生物链",
        },
    },
    "society": {
        "label": "社会结构",
        "fields": {
            "politics": "政治体制与权力架构",
            "economy": "经济模式与贸易",
            "class_system": "阶级/等级系统",
        },
    },
    "culture": {
        "label": "历史文化",
        "fields": {
            "history": "关键历史事件与时代背景",
            "religion": "宗教信仰体系",
            "taboos": "文化禁忌与违逆后果",
        },
    },
    "daily_life": {
        "label": "沉浸感细节",
        "fields": {
            "food_clothing": "衣食住行的日常细节",
            "language_slang": "俚语、口音与方言",
            "entertainment": "娱乐方式与消遣",
        },
    },
}

WORLDBUILDING_FIELD_SCOPE_HINTS: Dict[str, Dict[str, str]] = {
    "core_rules": {
        "power_system": "只写能力/科技体系的核心分类、运行目标和使用门槛；可简要带出代价但不要拆成多字段",
        "physics_rules": "只写时间流速、神经反馈、生理极限等底层规律；不要写训练资源和黑市",
        "magic_tech": "只写游戏舱、同步接口、引擎、服务器等技术如何运作；不要写政治经济",
    },
    "geography": {
        "terrain": "只写世界版图、地貌和空间边界；不要写资源清单和社会制度",
        "climate": "只写气候、天象、季节和环境对修炼的影响；不要写政治和经济",
        "resources": "只写资源分布在哪里、为何难取；不要写货币制度和市场交易",
        "ecology": "只写妖兽、灵植、生物链和环境危险；不要写人族阶级制度",
    },
    "society": {
        "politics": "只写统治结构和明面规则；不要写经济价格、宗教神话或日常生活",
        "economy": "只写货币、贸易、黑市和资源流通；不要写阶级身份大段定义",
        "class_system": "只写阶级层级和身份差异；不要写具体压迫手段细节",
    },
    "culture": {
        "history": "只写关键历史事件及遗留后果；不要写娱乐、教育和通信",
        "religion": "只写信仰叙事和神话如何服务秩序；不要写禁忌清单",
        "taboos": "只写禁忌、触犯后果和维稳用途；不要写完整历史",
    },
    "daily_life": {
        "food_clothing": "只写衣食住行和生活成本；不要写完整社会阶级",
        "language_slang": "只写方言、称呼、口头禅和说话习惯；必须给2-4个可入正文的短语",
        "entertainment": "只写娱乐、节庆、赌博、斗法观看等消遣；不要写教育通信",
    },
}

def schema_field_keys(dim_key: str) -> frozenset[str]:
    dim = WORLDBUILDING_DIMENSION_DEFS.get(dim_key, {})
    fields = dim.get("fields") or {}
    return frozenset(fields.keys())


def schema_field_order(dim_key: str) -> tuple[str, ...]:
    dim = WORLDBUILDING_DIMENSION_DEFS.get(dim_key, {})
    fields = dim.get("fields") or {}
    return tuple(fields.keys())


def resolve_canonical_field(dim_key: str, raw_key: str) -> str:
    """仅接受 schema 约定字段；未知字段不做猜测。"""
    key = str(raw_key).strip()
    return key if key in schema_field_keys(dim_key) else ""


def canonicalize_dimension_fields(
    dim_key: str,
    raw: Mapping[str, Any],
) -> Dict[str, str]:
    """维度 dict → 仅含 schema 规范字段键的中文段落。"""
    buckets: Dict[str, list[str]] = defaultdict(list)

    for raw_k, raw_v in raw.items():
        prose = worldbuilding_value_to_prose(raw_v)
        if not prose:
            continue
        target = resolve_canonical_field(dim_key, str(raw_k))
        if not target:
            continue
        if target in buckets and prose in buckets[target]:
            continue
        buckets[target].append(prose)

    return {k: "\n\n".join(parts) for k, parts in buckets.items() if parts}


@lru_cache(maxsize=None)
def _dimension_validation_model(dim_key: str) -> Any:
    fields = {
        field_key: (
            str,
            Field(
                min_length=MIN_WORLDBUILDING_FIELD_CHARS,
                max_length=MAX_WORLDBUILDING_FIELD_CHARS,
            ),
        )
        for field_key in schema_field_keys(dim_key)
    }
    if not fields:
        raise ValueError(f"Unknown worldbuilding dimension: {dim_key}")
    return create_model(
        f"Worldbuilding{dim_key.title().replace('_', '')}Dimension",
        __config__=ConfigDict(extra="ignore"),
        **fields,
    )


def validate_complete_dimension_fields(
    dim_key: str,
    fields: Mapping[str, Any],
) -> Dict[str, str]:
    """Return validated canonical fields, or ``{}`` when incomplete.

    This is the commit gate for generated worldbuilding content: JSON parsing
    proves syntax; this schema proves the dimension has every contract field
    and each value is long enough to be useful.
    """
    canonical = canonicalize_dimension_fields(dim_key, fields)
    try:
        model = _dimension_validation_model(dim_key)
        validated = model.model_validate(canonical)
    except (ValidationError, ValueError):
        return {}
    return {
        key: str(getattr(validated, key)).strip()
        for key in schema_field_order(dim_key)
    }


def build_fields_desc_for_prompt(dimension_keys: Any = None) -> str:
    """CPMS user.md 的 {fields_desc} 占位内容。"""
    lines: list[str] = []
    keys = tuple(dimension_keys or WORLD_BUILDING_DIMENSION_KEYS)
    for dim_key in keys:
        dim_def = WORLDBUILDING_DIMENSION_DEFS[dim_key]
        lines.append(f'    "{dim_key}": {{')
        fields = list(dim_def["fields"].items())
        for idx, (fk, desc) in enumerate(fields):
            comma = "," if idx < len(fields) - 1 else ""
            scope = WORLDBUILDING_FIELD_SCOPE_HINTS.get(dim_key, {}).get(fk, "")
            scope_text = f"{scope}；" if scope else ""
            lines.append(
                f'      "{fk}": "（{desc}。{scope_text}只写2-3句、80-160字、单段；不得换行；勿嵌套JSON或英文键）"{comma}'
            )
        dim_comma = "," if dim_key != keys[-1] else ""
        lines.append(f"    }}{dim_comma}")
    return "\n".join(lines)
