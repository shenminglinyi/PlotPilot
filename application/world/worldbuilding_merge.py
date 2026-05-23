"""
世界观数据合并：Bible.world_settings（维度·字段 扁平条目）与世界观表(Worldbuilding entity)对齐。

SSE 会从 LLM 生成「扩展字段」（超出 Worldbuilding ORM 的 15 个槽位）。
这些条目会写入 Bible；持久化表中只映射子集字段。若无合并，
读表会丢失 Bible 侧的完整内容——表现为「流式看到很多，入库/面板只有一条或很少」。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

WORLD_BUILDING_DIMENSION_KEYS: Tuple[str, ...] = (
    "core_rules",
    "geography",
    "society",
    "culture",
    "daily_life",
)

# API / 编辑器 UI 展示的「经典十五字段」与各维度扩充字段分界
_LEGACY_KEYS_BY_DIMENSION: Dict[str, Tuple[str, ...]] = {
    "core_rules": ("power_system", "physics_rules", "magic_tech"),
    "geography": ("terrain", "climate", "resources", "ecology"),
    "society": ("politics", "economy", "class_system"),
    "culture": ("history", "religion", "taboos"),
    "daily_life": ("food_clothing", "language_slang", "entertainment"),
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
    return {
        "core_rules": dict(wb.core_rules),
        "geography": dict(wb.geography),
        "society": dict(wb.society),
        "culture": dict(wb.culture),
        "daily_life": dict(wb.daily_life),
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
        desc = (getattr(s, "description", None) or "").strip()
        if desc:
            dims[dim][key] = desc
    return dims


def merge_worldbuilding_table_and_bible_slices(
    table_slices: Dict[str, Dict[str, str]],
    bible_slices: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    """以 Bible 为基底，用世界观表中「非空」字段覆盖同名键。

    这样 SSE 写入的多余字段可从 Bible 读回；用户在世界观面板改过并落库的键优先覆盖。
    """
    merged: Dict[str, Dict[str, str]] = {}
    for dim in WORLD_BUILDING_DIMENSION_KEYS:
        b_blk = bible_slices.get(dim) or {}
        t_blk = table_slices.get(dim) or {}
        out = dict(b_blk)
        for kk, vv in t_blk.items():
            s = "" if vv is None else str(vv).strip()
            if s:
                out[kk] = s
        merged[dim] = out
    return merged


def project_slices_to_legacy_api_shape(full_slices: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """将任意键的五维字典压成编辑器 / Worldbuilding API 展示的 15 个经典字段；

    LLM 多出来的键合并到每个维度的「最后一个」经典字段，避免凭空丢失正文。
    """
    out: Dict[str, Dict[str, str]] = {}
    for dim, keys in _LEGACY_KEYS_BY_DIMENSION.items():
        blk = full_slices.get(dim) or {}
        row = {
            k: text
            for k in keys
            if (text := str(blk.get(k) or "").strip())
        }
        extra_keys = frozenset(keys)
        extras = [(k, str(v).strip()) for k, v in sorted(blk.items()) if k not in extra_keys and str(v).strip()]
        if extras:
            appendix = "\n\n".join(f"【{k}】{v}" for k, v in extras)
            tail = keys[-1]
            base = row.get(tail, "")
            row[tail] = (base.rstrip() + "\n\n" + appendix) if base else appendix
        out[dim] = row
    return out
