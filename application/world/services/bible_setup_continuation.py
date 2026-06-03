"""Bible onboarding continuation handlers."""
from __future__ import annotations

from typing import Any, Mapping

from application.paths import get_db_path
from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler
from application.ai.llm_json_extract import parse_llm_json_to_any
from application.world.services.bible_service import BibleService
from application.world.services.worldbuilding_field_text import normalize_dimension_fields
from application.world.services.worldbuilding_service import WorldbuildingService
from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository


def _context_value(context: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = context.get(key, default)
    return default if value is None else value


def _parse_content(raw: str) -> dict[str, Any]:
    data, _ = parse_llm_json_to_any(raw)
    return data if isinstance(data, dict) else {}


def _parse_jsonish_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    parsed, _ = parse_llm_json_to_any(text)
    return parsed if parsed is not None else value


def _as_list(value: Any) -> list[Any]:
    value = _parse_jsonish_value(value)
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    value = _parse_jsonish_value(value)
    return dict(value) if isinstance(value, Mapping) else {}


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _extract_records(data: Any, key: str) -> list[Any]:
    if isinstance(data, Mapping):
        records = data.get(key)
    else:
        records = data
    return _as_list(records)


def _get_services(_context: ContinuationContext) -> tuple[BibleService, WorldbuildingService | None]:
    from interfaces.api.dependencies import get_bible_service

    bible_service = get_bible_service()
    try:
        worldbuilding_service = WorldbuildingService(WorldbuildingRepository(get_db_path()))
    except Exception:
        worldbuilding_service = None
    return bible_service, worldbuilding_service


def bible_worldbuilding_handler(context: ContinuationContext) -> Mapping[str, Any]:
    bible_service, worldbuilding_service = _get_services(context)
    novel_id = str(_context_value(context.session.context, "novel_id", ""))
    if not novel_id:
        return {}
    data = _parse_content(context.decision.accepted_content)
    style = str(data.get("style") or "").strip()
    worldbuilding = data.get("worldbuilding") if isinstance(data.get("worldbuilding"), Mapping) else {}
    if not worldbuilding:
        worldbuilding = {
            dim_key: data.get(dim_key)
            for dim_key in ("core_rules", "geography", "society", "culture", "daily_life")
            if isinstance(data.get(dim_key), Mapping)
        }
    result: dict[str, Any] = {"novel_id": novel_id}

    if style:
        bible_service.add_style_note(
            novel_id=novel_id,
            note_id=f"{novel_id}-style-1",
            category="文风公约",
            content=style,
        )
        result["style"] = style

    if worldbuilding and worldbuilding_service is not None:
        normalized = {}
        for dim_key in ("core_rules", "geography", "society", "culture", "daily_life"):
            block = worldbuilding.get(dim_key)
            if isinstance(block, Mapping):
                normalized[dim_key] = normalize_dimension_fields(block, dim_key=dim_key)
        if normalized:
            worldbuilding_service.update_worldbuilding(
                novel_id=novel_id,
                core_rules=normalized.get("core_rules"),
                geography=normalized.get("geography"),
                society=normalized.get("society"),
                culture=normalized.get("culture"),
                daily_life=normalized.get("daily_life"),
            )
            result["worldbuilding"] = normalized
            for dim_key, dim_value in normalized.items():
                result[dim_key] = dim_value
    return result


def bible_characters_handler(context: ContinuationContext) -> Mapping[str, Any]:
    bible_service, _ = _get_services(context)
    novel_id = str(_context_value(context.session.context, "novel_id", ""))
    if not novel_id:
        return {}
    data, _ = parse_llm_json_to_any(context.decision.accepted_content)
    characters = _extract_records(data, "characters")
    saved: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for idx, char_data in enumerate(characters):
        if not isinstance(char_data, Mapping):
            continue
        name = str(char_data.get("name") or "").strip()
        if not name:
            continue
        character_id = str(char_data.get("id") or f"{novel_id}-char-{idx + 1}")
        if character_id in used_ids:
            character_id = f"{novel_id}-char-{idx + 1}-{len(used_ids)}"
        used_ids.add(character_id)
        save_character = getattr(bible_service, "upsert_character", bible_service.add_character)
        save_character(
            novel_id=novel_id,
            character_id=character_id,
            name=name,
            description=f"{str(char_data.get('role') or '').strip()} - {str(char_data.get('description') or '').strip()}".strip(" -"),
            relationships=_as_list(char_data.get("relationships")),
            gender=_as_str(char_data.get("gender")),
            age=_as_str(char_data.get("age")),
            appearance=_as_str(char_data.get("appearance")),
            personality=_as_str(char_data.get("personality") or char_data.get("flaw")),
            background=_as_str(char_data.get("background") or char_data.get("ghost")),
            core_motivation=_as_str(char_data.get("core_motivation") or char_data.get("want")),
            inner_lack=_as_str(char_data.get("inner_lack") or char_data.get("need")),
            public_profile=_as_str(char_data.get("public_profile")),
            hidden_profile=_as_str(char_data.get("hidden_profile")),
            reveal_chapter=char_data.get("reveal_chapter"),
            mental_state=_as_str(char_data.get("mental_state"), "NORMAL") or "NORMAL",
            mental_state_reason=_as_str(char_data.get("mental_state_reason")),
            verbal_tic=_as_str(char_data.get("verbal_tic")),
            idle_behavior=_as_str(char_data.get("idle_behavior")),
            core_belief=_as_str(char_data.get("core_belief")),
            moral_taboos=_as_list(char_data.get("moral_taboos")),
            voice_profile=_as_dict(char_data.get("voice_profile")),
            active_wounds=_as_list(char_data.get("active_wounds")),
        )
        row = dict(char_data)
        row["id"] = character_id
        saved.append(row)

    protagonist = saved[0] if saved else {}
    return {"novel_id": novel_id, "characters": saved, "protagonist": protagonist, "existing_characters": saved}


def bible_locations_handler(context: ContinuationContext) -> Mapping[str, Any]:
    bible_service, _ = _get_services(context)
    novel_id = str(_context_value(context.session.context, "novel_id", ""))
    if not novel_id:
        return {}
    data, _ = parse_llm_json_to_any(context.decision.accepted_content)
    locations = _extract_records(data, "locations")
    saved: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for idx, loc_data in enumerate(locations):
        if not isinstance(loc_data, Mapping):
            continue
        name = str(loc_data.get("name") or "").strip()
        if not name:
            continue
        location_id = str(loc_data.get("id") or f"{novel_id}-loc-{idx + 1}")
        if location_id in used_ids:
            location_id = f"{novel_id}-loc-{idx + 1}-{len(used_ids)}"
        used_ids.add(location_id)
        prepared = {
            "location_id": location_id,
            "name": name,
            "description": str(loc_data.get("description") or ""),
            "location_type": str(loc_data.get("type") or loc_data.get("location_type") or "场景"),
            "parent_id": loc_data.get("parent_id"),
            "connections": _as_list(loc_data.get("connections")),
        }
        bible_service.add_location(
            novel_id=novel_id,
            location_id=prepared["location_id"],
            name=prepared["name"],
            description=prepared["description"],
            location_type=prepared["location_type"],
            connections=prepared["connections"],
            parent_id=prepared["parent_id"],
        )
        saved.append({**prepared, "id": location_id, "type": prepared["location_type"]})

    return {"novel_id": novel_id, "locations": saved, "existing_locations": saved}


def register_bible_setup_continuations() -> None:
    register_continuation_handler("bible_worldbuilding", bible_worldbuilding_handler)
    register_continuation_handler("bible_characters", bible_characters_handler)
    register_continuation_handler("bible_locations", bible_locations_handler)
