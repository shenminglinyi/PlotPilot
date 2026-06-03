"""Prompt variable declaration helpers for AI Invocation."""
from __future__ import annotations

import re
from typing import Any, Mapping

from application.ai_invocation.dtos import VariableBinding


PROMPT_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def alias_for_variable_key(variable_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", variable_key).strip("_") or "custom_variable"


def infer_variable_scope(variable_key: str) -> str:
    prefix = variable_key.split(".", 1)[0]
    if prefix in {"global", "novel", "chapter", "scene", "beat"}:
        return "global" if prefix == "global" else prefix
    return "runtime"


def infer_variable_stage(variable_key: str) -> str:
    if ".review" in variable_key:
        return "review"
    if ".planning" in variable_key or ".outline" in variable_key:
        return "planning"
    if ".setup" in variable_key or variable_key.startswith("novel."):
        return "setup"
    if ".postprocess" in variable_key:
        return "postprocess"
    return "writing"


def prompt_declared_variable_keys(system_template: str, user_template: str) -> set[str]:
    raw = set(PROMPT_VARIABLE_PATTERN.findall(system_template or ""))
    raw.update(PROMPT_VARIABLE_PATTERN.findall(user_template or ""))
    return {
        item.strip()
        for item in raw
        if item.strip() and not item.strip().startswith(("_", "%", "#"))
    }


def aliases_with_dotted_variables(aliases: Mapping[str, Any]) -> dict[str, Any]:
    expanded: dict[str, Any] = dict(aliases or {})
    for alias, value in aliases.items():
        key = str(alias or "")
        if "." not in key:
            continue
        cursor = expanded
        parts = [part for part in key.split(".") if part]
        for part in parts[:-1]:
            nested = cursor.get(part)
            if not isinstance(nested, dict):
                nested = {}
                cursor[part] = nested
            cursor = nested
        if parts:
            cursor[parts[-1]] = value
    return expanded


def prompt_declared_input_bindings(
    *,
    existing_bindings: list[VariableBinding],
    system_template: str,
    user_template: str,
) -> tuple[list[VariableBinding], list[dict[str, str]]]:
    bindings = list(existing_bindings)
    declared_keys = prompt_declared_variable_keys(system_template, user_template)
    if not declared_keys:
        return bindings, []

    bound_variable_keys = {binding.variable_key for binding in bindings if binding.variable_key}
    bound_aliases = {binding.alias for binding in bindings}
    added = []
    for variable_key in sorted(declared_keys):
        if variable_key in bound_variable_keys or variable_key in bound_aliases:
            continue
        alias = alias_for_variable_key(variable_key)
        if alias in bound_aliases:
            suffix = 2
            base = alias
            while f"{base}_{suffix}" in bound_aliases:
                suffix += 1
            alias = f"{base}_{suffix}"
        bindings.append(
            VariableBinding(
                alias=alias,
                variable_key=variable_key,
                required=True,
                default=None,
                source="prompt_draft",
                enabled=True,
                value_type="string",
                scope=infer_variable_scope(variable_key),
                stage=infer_variable_stage(variable_key),
                display_name=variable_key,
            )
        )
        bound_variable_keys.add(variable_key)
        bound_aliases.add(alias)
        added.append({"alias": alias, "variable_key": variable_key})
    return bindings, added
