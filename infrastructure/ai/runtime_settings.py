"""Runtime-persisted LLM settings shared by the API and provider resolution."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from application.paths import DATA_DIR


LLM_SETTINGS_PATH = DATA_DIR / "system" / "llm_settings.json"

DEFAULT_LLM_SETTINGS: Dict[str, Any] = {
    "vendor": "openai",
    "api_format": "openai_chat_completions",
    "base_url": "",
    "api_key": "",
    "model": "",
    "fast_model": "",
    "review_model": "",
    "scene_director_model": "",
    "state_extractor_model": "",
    "temperature": 0.7,
    "max_tokens": 4096,
    "timeout_ms": 300000,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings_from_env() -> Dict[str, Any]:
    provider = (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()
    if provider == "openai":
        vendor = "openai"
        api_format = "openai_chat_completions"
        base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        model = (os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "").strip()
    else:
        vendor = "claude"
        api_format = "anthropic_messages"
        base_url = (os.getenv("ANTHROPIC_BASE_URL") or "").strip()
        api_key = (
            os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_AUTH_TOKEN")
            or ""
        ).strip()
        model = (os.getenv("ANTHROPIC_MODEL") or os.getenv("LLM_MODEL") or "").strip()

    settings = deepcopy(DEFAULT_LLM_SETTINGS)
    settings.update(
        {
            "vendor": vendor,
            "api_format": api_format,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "fast_model": (os.getenv("FAST_LLM_MODEL") or "").strip(),
            "review_model": (os.getenv("REVIEW_LLM_MODEL") or "").strip(),
            "scene_director_model": (os.getenv("SCENE_DIRECTOR_MODEL") or "").strip(),
            "state_extractor_model": (os.getenv("STATE_EXTRACTOR_MODEL") or "").strip(),
            "temperature": _safe_float(os.getenv("LLM_TEMPERATURE"), DEFAULT_LLM_SETTINGS["temperature"]),
            "max_tokens": _safe_int(os.getenv("LLM_MAX_TOKENS"), DEFAULT_LLM_SETTINGS["max_tokens"]),
            "timeout_ms": _safe_int(os.getenv("LLM_TIMEOUT_MS"), DEFAULT_LLM_SETTINGS["timeout_ms"]),
        }
    )
    return settings


def _safe_int(value: Any, default: int) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_vendor(vendor: Any, api_format: str) -> str:
    raw = str(vendor or "").strip().lower()
    if raw:
        return raw
    if api_format == "anthropic_messages":
        return "claude"
    if api_format == "openai_responses":
        return "codex"
    return "openai"


def _normalize_format(api_format: Any) -> str:
    raw = str(api_format or "").strip().lower()
    if raw in {"anthropic_messages", "openai_chat_completions", "openai_responses"}:
        return raw
    if raw == "codex":
        return "openai_responses"
    return "anthropic_messages" if raw == "claude" else "openai_chat_completions"


def _normalize_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = deepcopy(DEFAULT_LLM_SETTINGS)
    settings.update(payload or {})

    settings["api_format"] = _normalize_format(settings.get("api_format"))
    settings["vendor"] = _normalize_vendor(settings.get("vendor"), settings["api_format"])

    for key in (
        "base_url",
        "api_key",
        "model",
        "fast_model",
        "review_model",
        "scene_director_model",
        "state_extractor_model",
    ):
        settings[key] = str(settings.get(key) or "").strip()

    settings["temperature"] = _safe_float(settings.get("temperature"), DEFAULT_LLM_SETTINGS["temperature"])
    settings["max_tokens"] = max(1, _safe_int(settings.get("max_tokens"), DEFAULT_LLM_SETTINGS["max_tokens"]))
    settings["timeout_ms"] = max(1000, _safe_int(settings.get("timeout_ms"), DEFAULT_LLM_SETTINGS["timeout_ms"]))
    return settings


def _masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _empty_store() -> Dict[str, Any]:
    return {
        "current": _settings_from_env(),
        "active_preset_id": None,
        "presets": [],
    }


def _normalize_preset(payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = _normalize_settings(payload.get("settings") or payload)
    return {
        "id": str(payload.get("id") or uuid4()),
        "name": str(payload.get("name") or "未命名预设").strip() or "未命名预设",
        "updated_at": str(payload.get("updated_at") or _now_iso()),
        "settings": settings,
    }


def load_llm_store() -> Dict[str, Any]:
    if not LLM_SETTINGS_PATH.exists():
        return _empty_store()

    try:
        payload = json.loads(LLM_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_store()

    if not isinstance(payload, dict):
        return _empty_store()

    if "current" not in payload and "presets" not in payload:
        return {
            "current": _normalize_settings(payload),
            "active_preset_id": None,
            "presets": [],
        }

    store = _empty_store()
    store["current"] = _normalize_settings(payload.get("current") or _settings_from_env())
    store["active_preset_id"] = payload.get("active_preset_id")
    store["presets"] = [
        _normalize_preset(item)
        for item in (payload.get("presets") or [])
        if isinstance(item, dict)
    ]

    preset_ids = {item["id"] for item in store["presets"]}
    if store["active_preset_id"] not in preset_ids:
        store["active_preset_id"] = None

    return store


def save_llm_store(store: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "current": _normalize_settings(store.get("current") or _settings_from_env()),
        "active_preset_id": store.get("active_preset_id"),
        "presets": [
            _normalize_preset(item)
            for item in (store.get("presets") or [])
            if isinstance(item, dict)
        ],
    }
    preset_ids = {item["id"] for item in normalized["presets"]}
    if normalized["active_preset_id"] not in preset_ids:
        normalized["active_preset_id"] = None

    _ensure_parent(LLM_SETTINGS_PATH)
    LLM_SETTINGS_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def load_llm_settings() -> Dict[str, Any]:
    return load_llm_store()["current"]


def save_llm_settings(payload: Dict[str, Any], active_preset_id: str | None = None) -> Dict[str, Any]:
    store = load_llm_store()
    store["current"] = _normalize_settings(payload)
    store["active_preset_id"] = active_preset_id
    return save_llm_store(store)["current"]


def save_llm_preset(
    *,
    name: str,
    settings: Dict[str, Any],
    preset_id: str | None = None,
    set_active: bool = False,
) -> Dict[str, Any]:
    store = load_llm_store()
    normalized_settings = _normalize_settings(settings)
    target_id = preset_id or str(uuid4())

    updated = False
    for preset in store["presets"]:
        if preset["id"] == target_id:
            preset["name"] = name.strip() or preset["name"]
            preset["updated_at"] = _now_iso()
            preset["settings"] = normalized_settings
            updated = True
            break

    if not updated:
        store["presets"].append(
            {
                "id": target_id,
                "name": name.strip() or "未命名预设",
                "updated_at": _now_iso(),
                "settings": normalized_settings,
            }
        )

    if set_active:
        store["current"] = normalized_settings
        store["active_preset_id"] = target_id

    return save_llm_store(store)


def activate_llm_preset(preset_id: str) -> Dict[str, Any]:
    store = load_llm_store()
    for preset in store["presets"]:
        if preset["id"] == preset_id:
            store["current"] = deepcopy(preset["settings"])
            store["active_preset_id"] = preset_id
            return save_llm_store(store)
    raise KeyError(preset_id)


def delete_llm_preset(preset_id: str) -> Dict[str, Any]:
    store = load_llm_store()
    store["presets"] = [preset for preset in store["presets"] if preset["id"] != preset_id]
    if store["active_preset_id"] == preset_id:
        store["active_preset_id"] = None
    return save_llm_store(store)


def _preset_response(preset: Dict[str, Any]) -> Dict[str, Any]:
    settings = deepcopy(preset["settings"])
    return {
        "id": preset["id"],
        "name": preset["name"],
        "updated_at": preset["updated_at"],
        "vendor": settings.get("vendor", ""),
        "api_format": settings.get("api_format", ""),
        "base_url": settings.get("base_url", ""),
        "api_key": "",
        "api_key_masked": _masked(settings.get("api_key", "")),
        "model": settings.get("model", ""),
        "fast_model": settings.get("fast_model", ""),
        "review_model": settings.get("review_model", ""),
        "scene_director_model": settings.get("scene_director_model", ""),
        "state_extractor_model": settings.get("state_extractor_model", ""),
        "temperature": settings.get("temperature", DEFAULT_LLM_SETTINGS["temperature"]),
        "max_tokens": settings.get("max_tokens", DEFAULT_LLM_SETTINGS["max_tokens"]),
        "timeout_ms": settings.get("timeout_ms", DEFAULT_LLM_SETTINGS["timeout_ms"]),
    }


def get_llm_settings_response() -> Dict[str, Any]:
    store = load_llm_store()
    settings = deepcopy(store["current"])
    settings["api_key_masked"] = _masked(settings.get("api_key", ""))
    settings["api_key"] = ""
    settings["active_preset_id"] = store.get("active_preset_id")
    settings["presets"] = [_preset_response(item) for item in store["presets"]]
    return settings
