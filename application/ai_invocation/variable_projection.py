"""Prompt-facing projections for structured Variable Hub values."""
from __future__ import annotations

import json
from typing import Any, Mapping


def render_variable_value(value: Any, *, render_mode: str = "raw", projection_key: str = "") -> Any:
    """Render a raw variable value for prompt consumption.

    Variable Hub keeps canonical values structured.  This helper creates stable
    prompt-facing aliases only when a binding explicitly asks for a projection
    or non-raw render mode.
    """
    key = str(projection_key or "").strip()
    mode = str(render_mode or "raw").strip().lower()
    if key:
        return _render_projection(value, key)
    if mode in {"raw", ""}:
        return value
    if mode == "json":
        return _to_json(value)
    if mode in {"text", "prompt_text"}:
        return _to_prompt_text(value)
    return value


def _render_projection(value: Any, projection_key: str) -> str:
    if projection_key in {"characters.brief", "novel.characters.brief"}:
        return _characters_brief(value)
    if projection_key in {"character.card", "protagonist.card"}:
        return _character_card(value)
    if projection_key in {"locations.brief", "novel.locations.brief"}:
        return _locations_brief(value)
    if projection_key in {"worldbuilding.dimension", "worldbuilding.brief"}:
        return _mapping_brief(value)
    if projection_key in {"worldbuilding.context", "novel.worldbuilding.context"}:
        return _worldbuilding_context(value)
    if projection_key in {"json", "tojson"}:
        return _to_json(value)
    return _to_prompt_text(value)


def _to_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value or "")


def _to_prompt_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        lines = []
        for item in value:
            text = _mapping_brief(item) if isinstance(item, Mapping) else str(item or "").strip()
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines)
    if isinstance(value, Mapping):
        return _mapping_brief(value)
    return str(value)


def _mapping_brief(value: Any) -> str:
    if not isinstance(value, Mapping):
        return str(value or "").strip()
    parts = []
    for key, raw in value.items():
        if raw in (None, "", [], {}):
            continue
        if isinstance(raw, (Mapping, list)):
            rendered = _to_json(raw)
        else:
            rendered = str(raw).strip()
        if rendered:
            parts.append(f"{key}: {rendered}")
    return "；".join(parts)


def _character_line(character: Mapping[str, Any]) -> str:
    name = str(character.get("name") or "").strip()
    if not name:
        return ""
    keys = (
        "role",
        "description",
        "public_profile",
        "core_belief",
        "core_motivation",
        "inner_lack",
    )
    parts = [str(character.get(key) or "").strip() for key in keys]
    parts = [part for part in parts if part]
    return f"{name}: {'；'.join(parts)}" if parts else name


def _characters_brief(value: Any) -> str:
    if not isinstance(value, list):
        return _to_prompt_text(value)
    lines = [
        _character_line(item)
        for item in value
        if isinstance(item, Mapping)
    ]
    return "\n".join(f"- {line}" for line in lines if line)


def _character_card(value: Any) -> str:
    if not isinstance(value, Mapping):
        return _to_prompt_text(value)
    field_labels = (
        ("name", "姓名"),
        ("role", "角色"),
        ("description", "定位"),
        ("public_profile", "公开身份"),
        ("hidden_profile", "隐藏信息"),
        ("core_belief", "核心信念"),
        ("core_motivation", "表层目标"),
        ("inner_lack", "内在缺口"),
        ("want", "想要"),
        ("need", "需要"),
        ("flaw", "弱点"),
        ("verbal_tic", "口头特征"),
        ("idle_behavior", "压力动作"),
    )
    lines = []
    for key, label in field_labels:
        raw = value.get(key)
        if raw in (None, "", [], {}):
            continue
        lines.append(f"- {label}: {raw}")
    voice = value.get("voice_profile")
    if isinstance(voice, Mapping) and voice:
        lines.append(f"- 声线: {_mapping_brief(voice)}")
    wounds = value.get("active_wounds")
    if isinstance(wounds, list) and wounds:
        lines.append(f"- 创伤触发: {_to_prompt_text(wounds)}")
    return "\n".join(lines)


def _locations_brief(value: Any) -> str:
    if not isinstance(value, list):
        return _to_prompt_text(value)
    lines = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        parts = [
            str(item.get("type") or "").strip(),
            str(item.get("description") or "").strip(),
        ]
        parts = [part for part in parts if part]
        lines.append(f"- {name}: {'；'.join(parts)}" if parts else f"- {name}")
    return "\n".join(lines)


def _worldbuilding_context(value: Any) -> str:
    if not isinstance(value, Mapping):
        return _to_prompt_text(value)
    labels = {
        "core_rules": "核心法则",
        "geography": "地理生态",
        "society": "社会结构",
        "culture": "历史文化",
        "daily_life": "沉浸感细节",
    }
    lines = []
    for key, label in labels.items():
        raw = value.get(key)
        if raw in (None, "", [], {}):
            continue
        lines.append(f"【{label}】\n{_to_prompt_text(raw)}")
    return "\n\n".join(lines)
