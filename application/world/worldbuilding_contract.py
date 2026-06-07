"""世界观字段契约配置读取。"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


_CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "shared"
    / "taxonomy"
    / "worldbuilding_contract_cn_v1.yaml"
)


@dataclass(frozen=True)
class WorldbuildingContract:
    """世界观字段契约。"""

    dimensions: Dict[str, Dict[str, Any]]
    field_scope_hints: Dict[str, Dict[str, str]]
    json_key_labels: Dict[str, str]


def _coerce_text_mapping(value: object) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


@lru_cache(maxsize=1)
def get_worldbuilding_contract() -> WorldbuildingContract:
    """读取世界观字段契约配置。"""
    data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    raw_dimensions = data.get("dimensions") if isinstance(data, dict) else {}
    dimensions: Dict[str, Dict[str, Any]] = {}
    scope_hints: Dict[str, Dict[str, str]] = {}

    if isinstance(raw_dimensions, dict):
        for dim_key, raw_dim in raw_dimensions.items():
            if not isinstance(raw_dim, dict):
                continue
            key = str(dim_key).strip()
            fields = _coerce_text_mapping(raw_dim.get("fields"))
            if not key or not fields:
                continue
            dimensions[key] = {
                "label": str(raw_dim.get("label") or key).strip(),
                "fields": fields,
            }
            scope_hints[key] = _coerce_text_mapping(raw_dim.get("scope_hints"))

    labels = _coerce_text_mapping(data.get("json_key_labels") if isinstance(data, dict) else {})
    return WorldbuildingContract(
        dimensions=dimensions,
        field_scope_hints=scope_hints,
        json_key_labels=labels,
    )
