"""在任意 JSON 子树中按「键名约定」改写章号整数，避免为每种快照结构写死解析代码。"""
from __future__ import annotations

from typing import Any, FrozenSet

from domain.novel.value_objects.chapter_renumber_spec import ChapterRenumberSpec

# 默认识别的「整型章号」字段名；新表/新 JSON 只需把键加进集合或通过协调器注入扩展键。
DEFAULT_CHAPTER_INTEGER_JSON_KEYS: FrozenSet[str] = frozenset(
    {
        "chapter_number",
        "chapter",
        "planted_in_chapter",
        "resolved_in_chapter",
        "suggested_resolve_chapter",
        "consumed_at_chapter",
        "first_appearance",
        "target_chapter_start",
        "target_chapter_end",
        "estimated_chapter_start",
        "estimated_chapter_end",
        "current_chapter",
        "last_updated_chapter",
        "resolve_chapter_window",
    }
)


def renumber_chapter_integers_in_json(
    obj: Any,
    spec: ChapterRenumberSpec,
    *,
    keys: FrozenSet[str] = DEFAULT_CHAPTER_INTEGER_JSON_KEYS,
) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in keys and isinstance(v, int) and not isinstance(v, bool):
                out[k] = spec.shift_chapter_ref(v)
            else:
                out[k] = renumber_chapter_integers_in_json(v, spec, keys=keys)
        return out
    if isinstance(obj, list):
        return [renumber_chapter_integers_in_json(x, spec, keys=keys) for x in obj]
    if isinstance(obj, tuple):
        return tuple(renumber_chapter_integers_in_json(x, spec, keys=keys) for x in obj)
    return obj
