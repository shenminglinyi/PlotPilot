"""世界观数据合并：Bible.world_settings 与 Worldbuilding 表对齐。

世界观字段契约与共享配置保持一致；配置之外的扩展键在读取边界过滤，
避免污染前端和写作上下文。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from application.world.worldbuilding_contract import get_worldbuilding_contract


_WORLDBUILDING_CONTRACT = get_worldbuilding_contract()

WORLD_BUILDING_DIMENSION_KEYS: Tuple[str, ...] = tuple(_WORLDBUILDING_CONTRACT.dimensions.keys())

WORLD_BUILDING_FIELD_KEYS_BY_DIMENSION: Dict[str, Tuple[str, ...]] = {
    dim_key: tuple((dim_cfg.get("fields") or {}).keys())
    for dim_key, dim_cfg in _WORLDBUILDING_CONTRACT.dimensions.items()
}


def empty_worldbuilding_slices() -> Dict[str, Dict[str, str]]:
    return {k: {} for k in WORLD_BUILDING_DIMENSION_KEYS}


def worldbuilding_slices_nonempty(slices: Optional[Dict[str, Any]]) -> bool:
    if not slices:
        return False
    for dim in WORLD_BUILDING_DIMENSION_KEYS:
        block = slices.get(dim)
        if not isinstance(block, dict):
            continue
        if any(str(v).strip() for v in block.values()):
            return True
    return False


def worldbuilding_entity_to_slices(wb: Any) -> Dict[str, Dict[str, str]]:
    """从世界观 ORM 实体得到五维 dict（仅为表内可表达的键）。"""
    if wb is None:
        return empty_worldbuilding_slices()
    raw = {
        "core_rules": dict(wb.core_rules),
        "geography": dict(wb.geography),
        "society": dict(wb.society),
        "culture": dict(wb.culture),
        "daily_life": dict(wb.daily_life),
    }
    return {
        dim: {
            k: v
            for k, v in (raw.get(dim) or {}).items()
            if k in WORLD_BUILDING_FIELD_KEYS_BY_DIMENSION.get(dim, ())
        }
        for dim in WORLD_BUILDING_DIMENSION_KEYS
    }


def bible_dto_world_settings_to_slices(bible: Any) -> Dict[str, Dict[str, str]]:
    """从 Bible DTO（含 world_setting.name=`维度.字段`）还原五维 dict。"""
    dims = empty_worldbuilding_slices()
    dim_keys = frozenset(WORLD_BUILDING_DIMENSION_KEYS)
    if bible is None:
        return dims
    for s in bible.world_settings or []:
        name = (getattr(s, "name", None) or "").strip()
        dot = name.find(".")
        if dot < 0:
            continue
        dim, key = name[:dot], name[dot + 1 :].strip()
        if dim not in dim_keys or not key:
            continue
        if key not in WORLD_BUILDING_FIELD_KEYS_BY_DIMENSION.get(dim, ()):
            continue
        desc = (getattr(s, "description", None) or "").strip()
        if desc:
            dims[dim][key] = desc
    return dims


def merge_worldbuilding_table_and_bible_slices(
    table_slices: Dict[str, Dict[str, str]],
    bible_slices: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    """以 Bible 为基底，用世界观表中「非空」字段覆盖同名键。

    用户在世界观面板改过并落库的键优先覆盖；非 writer 基础字段在边界过滤。
    """
    merged: Dict[str, Dict[str, str]] = {}
    for dim in WORLD_BUILDING_DIMENSION_KEYS:
        b_blk = bible_slices.get(dim) or {}
        t_blk = table_slices.get(dim) or {}
        allowed = frozenset(WORLD_BUILDING_FIELD_KEYS_BY_DIMENSION.get(dim, ()))
        out = {k: v for k, v in b_blk.items() if k in allowed}
        for kk, vv in t_blk.items():
            if kk not in allowed:
                continue
            s = "" if vv is None else str(vv).strip()
            if s:
                out[kk] = s
        merged[dim] = out
    return merged


def project_slices_to_contract_api_shape(full_slices: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """将五维字典压成共享契约字段；丢弃配置之外的扩展键。"""
    out: Dict[str, Dict[str, str]] = {}
    for dim, keys in WORLD_BUILDING_FIELD_KEYS_BY_DIMENSION.items():
        blk = full_slices.get(dim) or {}
        row = {
            k: text
            for k in keys
            if (text := str(blk.get(k) or "").strip())
        }
        out[dim] = row
    return out
