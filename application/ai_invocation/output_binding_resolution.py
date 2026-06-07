"""Helpers for resolving accepted JSON content against output bindings."""
from __future__ import annotations

from typing import Any, Mapping

from application.ai.llm_json_extract import parse_llm_json_to_any
from application.ai_invocation.dtos import InvocationSession, VariableBinding
from application.ai_invocation.variable_hub import extract_path_value


def parse_accepted_json(raw: str) -> Any:
    parsed, _ = parse_llm_json_to_any(raw or "")
    return parsed


def load_session_output_bindings(session: InvocationSession) -> list[VariableBinding]:
    binding_set_id = ""
    node_key = session.node_key
    if session.prompt_snapshot is not None:
        binding_set_id = session.prompt_snapshot.output_binding_set_id
        node_key = session.prompt_snapshot.node_key or node_key
    if not binding_set_id:
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
            SqliteInvocationSpecRepository,
            SqliteVariableHubRepository,
        )

        spec = SqliteInvocationSpecRepository(get_database()).get(session.operation, session.node_key)
        if spec is None or not spec.output_binding_set_id:
            return []
        binding_set_id = spec.output_binding_set_id
        node_key = spec.node_key
    if not binding_set_id:
        return []
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

    return SqliteVariableHubRepository(get_database()).get_output_bindings(binding_set_id, node_key)


def collect_dotted_children(payload: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    normalized = str(key or "").strip()
    if not normalized:
        return None
    if normalized in payload:
        value = payload.get(normalized)
        return value if isinstance(value, dict) else None
    prefix = f"{normalized}."
    entries = [(entry_key, entry_value) for entry_key, entry_value in payload.items() if entry_key.startswith(prefix)]
    if not entries:
        return None
    root: dict[str, Any] = {}
    for entry_key, entry_value in entries:
        remainder = entry_key[len(prefix):]
        parts = [part for part in remainder.split(".") if part]
        if not parts:
            continue
        cursor = root
        for part in parts[:-1]:
            next_value = cursor.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                cursor[part] = next_value
            cursor = next_value
        cursor[parts[-1]] = entry_value
    return root or None


def resolve_output_payload_value(payload: Any, *candidates: str) -> Any:
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if not normalized:
            continue
        if isinstance(payload, Mapping):
            if normalized in payload:
                return payload.get(normalized)
            dotted = collect_dotted_children(payload, normalized)
            if dotted is not None:
                return dotted
        value = extract_path_value(payload, normalized)
        if value is not None:
            return value
    return None


def extract_bound_output_values(
    payload: Any,
    bindings: list[VariableBinding],
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_alias: dict[str, Any] = {}
    by_variable_key: dict[str, Any] = {}
    for binding in bindings:
        if not binding.enabled:
            continue
        raw_value = resolve_output_payload_value(
            payload,
            binding.source_path or binding.alias,
            binding.alias if binding.source_path else "",
            binding.variable_key,
            "$" if binding.source_path in {"$", "$."} else "",
        )
        if raw_value is None:
            continue
        by_alias[binding.alias] = raw_value
        if binding.variable_key:
            by_variable_key[binding.variable_key] = raw_value
    return by_alias, by_variable_key

