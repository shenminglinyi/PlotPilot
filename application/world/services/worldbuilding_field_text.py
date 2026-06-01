"""世界观字段值规范化：嵌套 JSON → 可读中文段落（禁止 UI 出现英文键与 dict 字面量）。"""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping

from application.world.worldbuilding_contract import get_worldbuilding_contract

# LLM 常在值里使用的英文键 → 展示用中文标签，由共享配置资产驱动。
_JSON_KEY_LABELS: Dict[str, str] = get_worldbuilding_contract().json_key_labels


def _label_for_key(key: str) -> str:
    if key in _JSON_KEY_LABELS:
        return _JSON_KEY_LABELS[key]
    if all(ord(c) < 128 for c in key):
        return key.replace("_", " ")
    return key


def worldbuilding_value_to_prose(value: Any, *, depth: int = 0) -> str:
    """将任意 LLM 字段值转为中文可读正文。"""
    if value is None:
        return ""
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                parsed = json.loads(s)
                return worldbuilding_value_to_prose(parsed, depth=depth)
            except (json.JSONDecodeError, TypeError):
                pass
        return s
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = []
        for i, item in enumerate(value, 1):
            block = worldbuilding_value_to_prose(item, depth=depth + 1)
            if not block:
                continue
            if depth == 0 and len(value) > 1:
                parts.append(f"{i}. {block}")
            else:
                parts.append(block)
        return "\n".join(parts)
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if v is None or v == "" or v == [] or v == {}:
                continue
            label = _label_for_key(str(k))
            body = worldbuilding_value_to_prose(v, depth=depth + 1)
            if not body:
                continue
            if depth == 0:
                parts.append(f"【{label}】{body}")
            else:
                parts.append(f"{label}：{body}")
        return "\n".join(parts)
    return str(value).strip()


def normalize_dimension_fields(
    dim_data: Mapping[str, Any],
    *,
    dim_key: str | None = None,
) -> Dict[str, str]:
    """维度内所有字段 → 非空中文字符串。

    若提供 ``dim_key``，会将 LLM 自创键（name/essence/core_cost 等）合并到 schema 规范字段。
    """
    if dim_key:
        from application.world.worldbuilding_schema import canonicalize_dimension_fields

        return canonicalize_dimension_fields(dim_key, dim_data)

    out: Dict[str, str] = {}
    for k, v in dim_data.items():
        key = str(k).strip()
        if not key:
            continue
        prose = worldbuilding_value_to_prose(v)
        if prose:
            out[key] = prose
    return out
