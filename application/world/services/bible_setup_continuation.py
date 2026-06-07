"""Bible onboarding continuation handlers."""
from __future__ import annotations

from typing import Any, Mapping

from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler
from application.ai.llm_json_extract import parse_llm_json_to_any
from application.ai_invocation.output_binding_resolution import (
    extract_bound_output_values,
    load_session_output_bindings,
)
from application.world.dtos.bible_dto import CharacterDTO, LocationDTO, StyleNoteDTO
from application.world.worldbuilding_schema import validate_complete_dimension_fields


WORLDBUILDING_DIMENSION_KEYS = ("core_rules", "geography", "society", "culture", "daily_life")


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


def _coerce_worldbuilding_dimension(dim_key: str, value: Any) -> dict[str, Any]:
    value = _parse_jsonish_value(value)
    if isinstance(value, Mapping):
        return validate_complete_dimension_fields(dim_key, value)
    return {}


def _extract_records(data: Any, key: str) -> list[Any]:
    if isinstance(data, Mapping):
        records = data.get(key)
    else:
        records = data
    return _as_list(records)


def _bound_value_map(context: ContinuationContext, payload: Any) -> dict[str, Any]:
    bindings = load_session_output_bindings(context.session)
    _, by_variable_key = extract_bound_output_values(payload, bindings)
    return by_variable_key


def _get_services(_context: ContinuationContext):
    from application.paths import get_db_path
    from application.world.services.bible_location_triple_sync import BibleLocationTripleSyncService
    from application.world.services.bible_service import BibleService
    from application.world.services.worldbuilding_service import WorldbuildingService
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository
    from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
    from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
    from infrastructure.persistence.database.triple_repository import TripleRepository
    from infrastructure.persistence.database.unified_character_repository import SqliteUnifiedCharacterRepository
    from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository

    db = get_database()
    bible_service = BibleService(
        SqliteBibleRepository(db),
        novel_repository=SqliteNovelRepository(db),
        chapter_repository=SqliteChapterRepository(db),
        location_triple_sync=BibleLocationTripleSyncService(TripleRepository(db)),
        unified_character_repository=SqliteUnifiedCharacterRepository(db),
    )
    worldbuilding_service = WorldbuildingService(WorldbuildingRepository(get_db_path()))
    return bible_service, worldbuilding_service


def _refresh_shared_state(novel_id: str) -> None:
    if not novel_id:
        return
    try:
        from application.engine.services.state_bootstrap import refresh_narrative_contract_in_shared_state

        refresh_narrative_contract_in_shared_state(novel_id)
    except Exception:
        pass


def _compose_character_description(role: str, description: str) -> str:
    role_text = str(role or "").strip()
    desc_text = str(description or "").strip()
    if not role_text:
        return desc_text
    if not desc_text:
        return role_text
    if desc_text.startswith(f"{role_text} - "):
        return desc_text
    return f"{role_text} - {desc_text}"


def bible_worldbuilding_handler(context: ContinuationContext) -> Mapping[str, Any]:
    novel_id = str(_context_value(context.session.context, "novel_id", ""))
    if not novel_id:
        return {}
    data = _parse_content(context.decision.accepted_content)
    by_variable_key = _bound_value_map(context, data)
    style = str(by_variable_key.get("worldbuilding.style") or data.get("style") or "").strip()
    bound_worldbuilding = by_variable_key.get("worldbuilding.content")
    worldbuilding_value = bound_worldbuilding if bound_worldbuilding is not None else data.get("worldbuilding")
    worldbuilding_value = _parse_jsonish_value(worldbuilding_value)
    worldbuilding = dict(worldbuilding_value) if isinstance(worldbuilding_value, Mapping) else {}
    for dim_key in WORLDBUILDING_DIMENSION_KEYS:
        dim_value = by_variable_key.get(f"worldbuilding.{dim_key}")
        if dim_value is not None:
            worldbuilding[dim_key] = dim_value
    if not worldbuilding:
        worldbuilding = {
            dim_key: by_variable_key.get(f"worldbuilding.{dim_key}", data.get(dim_key))
            for dim_key in WORLDBUILDING_DIMENSION_KEYS
            if by_variable_key.get(f"worldbuilding.{dim_key}", data.get(dim_key)) is not None
        }
    normalized = {
        dim_key: coerced
        for dim_key, block in worldbuilding.items()
        if dim_key in WORLDBUILDING_DIMENSION_KEYS
        for coerced in [_coerce_worldbuilding_dimension(dim_key, block)]
        if coerced
    }
    result: dict[str, Any] = {"novel_id": novel_id}
    if style:
        result["style"] = style
    if normalized:
        result["worldbuilding"] = normalized
        for dim_key, dim_value in normalized.items():
            result[dim_key] = dim_value
    bible_service, worldbuilding_service = _get_services(context)
    if normalized:
        worldbuilding_service.update_worldbuilding(
            novel_id=novel_id,
            core_rules=normalized.get("core_rules"),
            geography=normalized.get("geography"),
            society=normalized.get("society"),
            culture=normalized.get("culture"),
            daily_life=normalized.get("daily_life"),
        )
    bible = bible_service.ensure_bible_for_novel(novel_id)
    style_notes = bible.style_notes
    if style:
        style_notes = [
            StyleNoteDTO(
                id=f"{novel_id}-style-1",
                category="文风公约",
                content=style,
            )
        ]
    bible_service.update_bible(
        novel_id=novel_id,
        characters=bible.characters,
        world_settings=bible.world_settings,
        locations=bible.locations,
        timeline_notes=bible.timeline_notes,
        style_notes=style_notes,
    )
    _refresh_shared_state(novel_id)
    return result


def bible_characters_handler(context: ContinuationContext) -> Mapping[str, Any]:
    novel_id = str(_context_value(context.session.context, "novel_id", ""))
    if not novel_id:
        return {}
    data, _ = parse_llm_json_to_any(context.decision.accepted_content)
    by_variable_key = _bound_value_map(context, data)
    characters = _as_list(by_variable_key.get("characters.list")) or _extract_records(data, "characters")
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
        row = dict(char_data)
        row["id"] = character_id
        row["relationships"] = _as_list(row.get("relationships"))
        row["moral_taboos"] = _as_list(row.get("moral_taboos"))
        row["voice_profile"] = _as_dict(row.get("voice_profile"))
        row["active_wounds"] = _as_list(row.get("active_wounds"))
        saved.append(row)

    protagonist = saved[0] if saved else {}
    bible_service, _ = _get_services(context)
    bible = bible_service.ensure_bible_for_novel(novel_id)
    characters = [
        CharacterDTO(
            id=str(row.get("id") or f"{novel_id}-char-{idx + 1}"),
            name=str(row.get("name") or "").strip(),
            description=_compose_character_description(
                str(row.get("role") or ""),
                str(row.get("description") or ""),
            ),
            relationships=_as_list(row.get("relationships")),
            gender=_as_str(row.get("gender")),
            age=_as_str(row.get("age")),
            appearance=_as_str(row.get("appearance")),
            personality=_as_str(row.get("personality") or row.get("flaw")),
            background=_as_str(row.get("background") or row.get("ghost")),
            core_motivation=_as_str(row.get("core_motivation") or row.get("want")),
            inner_lack=_as_str(row.get("inner_lack") or row.get("need")),
            public_profile=_as_str(row.get("public_profile")),
            hidden_profile=_as_str(row.get("hidden_profile")),
            reveal_chapter=row.get("reveal_chapter"),
            mental_state=_as_str(row.get("mental_state"), "NORMAL") or "NORMAL",
            mental_state_reason=_as_str(row.get("mental_state_reason")),
            verbal_tic=_as_str(row.get("verbal_tic")),
            idle_behavior=_as_str(row.get("idle_behavior")),
            core_belief=_as_str(row.get("core_belief")),
            moral_taboos=_as_list(row.get("moral_taboos")),
            voice_profile=_as_dict(row.get("voice_profile")),
            active_wounds=_as_list(row.get("active_wounds")),
        )
        for idx, row in enumerate(saved)
        if str(row.get("name") or "").strip()
    ]
    bible_service.update_bible(
        novel_id=novel_id,
        characters=characters,
        world_settings=bible.world_settings,
        locations=bible.locations,
        timeline_notes=bible.timeline_notes,
        style_notes=bible.style_notes,
    )
    _refresh_shared_state(novel_id)
    return {"novel_id": novel_id, "characters": saved, "protagonist": protagonist, "existing_characters": saved}


def bible_locations_handler(context: ContinuationContext) -> Mapping[str, Any]:
    novel_id = str(_context_value(context.session.context, "novel_id", ""))
    if not novel_id:
        return {}
    data, _ = parse_llm_json_to_any(context.decision.accepted_content)
    by_variable_key = _bound_value_map(context, data)
    locations = _as_list(by_variable_key.get("locations.list")) or _extract_records(data, "locations")
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
        saved.append(
            {
                "id": location_id,
                "name": name,
                "description": str(loc_data.get("description") or ""),
                "type": str(loc_data.get("type") or loc_data.get("location_type") or "场景"),
                "parent_id": loc_data.get("parent_id"),
                "connections": _as_list(loc_data.get("connections")),
            }
        )

    bible_service, _ = _get_services(context)
    bible = bible_service.ensure_bible_for_novel(novel_id)
    locations = [
        LocationDTO(
            id=str(row.get("id") or f"{novel_id}-loc-{idx + 1}"),
            name=str(row.get("name") or "").strip(),
            description=str(row.get("description") or ""),
            location_type=str(row.get("type") or row.get("location_type") or "场景"),
            parent_id=row.get("parent_id"),
        )
        for idx, row in enumerate(saved)
        if str(row.get("name") or "").strip()
    ]
    bible_service.update_bible(
        novel_id=novel_id,
        characters=bible.characters,
        world_settings=bible.world_settings,
        locations=locations,
        timeline_notes=bible.timeline_notes,
        style_notes=bible.style_notes,
    )
    _refresh_shared_state(novel_id)
    return {"novel_id": novel_id, "locations": saved, "existing_locations": saved}


def register_bible_setup_continuations() -> None:
    register_continuation_handler("bible_worldbuilding", bible_worldbuilding_handler)
    register_continuation_handler("bible_characters", bible_characters_handler)
    register_continuation_handler("bible_locations", bible_locations_handler)
