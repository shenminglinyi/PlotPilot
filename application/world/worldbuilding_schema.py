"""世界观五维 schema（单一数据源）。"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Any, Dict, Mapping

from pydantic import ConfigDict, Field, ValidationError, create_model

from application.world.services.worldbuilding_field_text import worldbuilding_value_to_prose
from application.world.worldbuilding_contract import get_worldbuilding_contract
from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS

MIN_WORLDBUILDING_FIELD_CHARS = 20
MAX_WORLDBUILDING_FIELD_CHARS = 500

_WORLDBUILDING_CONTRACT = get_worldbuilding_contract()

# 与 AutoBibleGenerator / CPMS fields_desc 一致，由共享配置资产驱动。
WORLDBUILDING_DIMENSION_DEFS: Dict[str, Dict[str, Any]] = _WORLDBUILDING_CONTRACT.dimensions
WORLDBUILDING_FIELD_SCOPE_HINTS: Dict[str, Dict[str, str]] = (
    _WORLDBUILDING_CONTRACT.field_scope_hints
)

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
