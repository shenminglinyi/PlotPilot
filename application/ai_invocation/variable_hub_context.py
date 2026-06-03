"""Prompt-facing Variable Hub context helpers."""
from __future__ import annotations

import json
from typing import Any, Mapping


SETUP_VARIABLE_PREFIXES = (
    "novel.setup.",
    "novel.worldbuilding",
    "novel.characters.",
    "novel.locations.",
    "novel.plot.",
)
SETUP_VARIABLE_KEYS = frozenset({"novel.style.guide"})


def is_setup_guide_variable(variable_key: str) -> bool:
    key = str(variable_key or "").strip()
    return key in SETUP_VARIABLE_KEYS or key.startswith(SETUP_VARIABLE_PREFIXES)


def format_setup_variable_hub_context(snapshot_items: Any) -> str:
    """Render setup-guide Variable Hub values as a compact prompt block."""
    lines: list[str] = []
    seen: set[str] = set()
    for raw in snapshot_items or ():
        if not isinstance(raw, Mapping):
            continue
        variable_key = str(raw.get("variable_key") or raw.get("key") or "").strip()
        if not variable_key or variable_key in seen or not is_setup_guide_variable(variable_key):
            continue
        value = raw.get("value")
        if value in (None, "", [], {}):
            continue
        seen.add(variable_key)
        display_name = str(raw.get("display_name") or raw.get("key") or variable_key).strip()
        lines.append(f"【{display_name}】{variable_key}")
        lines.append(_format_value(value))
    return "\n\n".join(lines)


def inject_setup_variable_hub_context(prompt_user: str, context_block: str) -> str:
    text = str(prompt_user or "")
    context = str(context_block or "").strip()
    if not context or context in text:
        return text
    header = "变量中心（新书引导已确认内容）："
    if header in text:
        return text
    return f"{header}\n{context}\n\n{text}"


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)
