"""Prompt variable declaration helpers for AI Invocation."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from application.ai_invocation.dtos import VariableBinding


PROMPT_VARIABLE_PATTERN = re.compile(
    r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:(?:\.[a-zA-Z_][a-zA-Z0-9_]*)|(?:\[-?\d+\]))*)\s*(?:\|[^{}]*)?\}\}"
)
LEGACY_VARIABLE_PATTERN = re.compile(
    r"(?<!\{)\{(?!\{)(?!\s*[%#])\s*([a-zA-Z_][a-zA-Z0-9_]*(?:(?:\.[a-zA-Z_][a-zA-Z0-9_]*)|(?:\[-?\d+\]))*)\s*\}(?!\})"
)


class PromptValueView:
    """Expose structured values in templates while preserving whole-value text."""

    def __init__(self, raw_value: Any, rendered_value: Any):
        self._raw_value = raw_value
        self._rendered_value = rendered_value

    def __str__(self) -> str:
        if self._rendered_value is None:
            return ""
        if isinstance(self._raw_value, (Mapping, list, tuple)) and self._rendered_value is self._raw_value:
            try:
                return json.dumps(self._raw_value, ensure_ascii=False, indent=2, default=str)
            except Exception:
                return str(self._rendered_value)
        return str(self._rendered_value)

    def __repr__(self) -> str:
        return str(self)

    def __bool__(self) -> bool:
        return bool(self._raw_value) or bool(self._rendered_value)

    def __len__(self) -> int:
        if isinstance(self._raw_value, (Mapping, list, tuple, str)):
            return len(self._raw_value)
        return 0

    def __iter__(self):
        if isinstance(self._raw_value, Mapping):
            return iter(self._raw_value)
        if isinstance(self._raw_value, (list, tuple)):
            return iter(self._raw_value)
        return iter(())

    def __getitem__(self, key: Any) -> Any:
        if isinstance(self._raw_value, Mapping):
            return self._raw_value[key]
        if isinstance(self._raw_value, (list, tuple)):
            return self._raw_value[key]
        raise KeyError(key)

    def __getattr__(self, key: str) -> Any:
        if isinstance(self._raw_value, Mapping) and key in self._raw_value:
            return self._raw_value[key]
        raise AttributeError(key)


def alias_for_variable_key(variable_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", variable_key).strip("_") or "custom_variable"


def prompt_reference_root(reference: str) -> str:
    match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)", str(reference or "").strip())
    return match.group(1) if match else ""


def normalize_declared_variable_reference(reference: str, known_variable_keys: set[str] | list[str] | tuple[str, ...]) -> str:
    """Collapse structured access back to a declared root variable when possible."""
    normalized = str(reference or "").strip()
    if not normalized:
        return normalized
    known = {str(item or "").strip() for item in known_variable_keys if str(item or "").strip()}
    if normalized in known:
        return normalized
    matches = [
        candidate
        for candidate in known
        if normalized.startswith(f"{candidate}.") or normalized.startswith(f"{candidate}[")
    ]
    if not matches:
        return normalized
    return max(matches, key=len)


def normalize_declared_variable_keys(
    declared_keys: set[str] | list[str] | tuple[str, ...],
    known_variable_keys: set[str] | list[str] | tuple[str, ...],
) -> set[str]:
    return {
        normalized
        for normalized in (
            normalize_declared_variable_reference(reference, known_variable_keys)
            for reference in declared_keys
        )
        if normalized
    }


def infer_variable_scope(variable_key: str) -> str:
    prefix = variable_key.split(".", 1)[0]
    if prefix == "global":
        return "global"
    if prefix in {"novel", "worldbuilding", "characters", "locations", "plot"}:
        return "novel"
    if prefix in {"chapter", "scene", "beat"}:
        return prefix
    return "runtime"


def infer_variable_stage(variable_key: str) -> str:
    if variable_key.startswith("plot.") or ".plot." in variable_key:
        return "planning"
    if variable_key.startswith("worldbuilding.") or ".worldbuilding." in variable_key:
        return "worldbuilding"
    if variable_key.startswith("characters.") or ".characters." in variable_key:
        return "characters"
    if variable_key.startswith("locations.") or ".locations." in variable_key:
        return "locations"
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
    raw.update(LEGACY_VARIABLE_PATTERN.findall(system_template or ""))
    raw.update(LEGACY_VARIABLE_PATTERN.findall(user_template or ""))
    return {
        item.strip()
        for item in raw
        if item.strip() and not item.strip().startswith(("_", "%", "#"))
    }


def is_reference_to_existing_binding(reference: str, bindings: list[VariableBinding]) -> bool:
    """Return True when a template reference is an access on a bound variable."""
    normalized = str(reference or "").strip()
    if not normalized:
        return False
    root = prompt_reference_root(normalized)
    bound_aliases = {binding.alias for binding in bindings if binding.enabled and binding.alias}
    if root in bound_aliases:
        return True
    for binding in bindings:
        variable_key = str(binding.variable_key or "").strip()
        if not binding.enabled or not variable_key:
            continue
        if normalized == variable_key:
            return True
        if normalized.startswith(f"{variable_key}.") or normalized.startswith(f"{variable_key}["):
            return True
    return False


def public_aliases_for_binding(binding: VariableBinding) -> set[str]:
    aliases = {str(binding.alias or "").strip(), str(binding.variable_key or "").strip()}
    for key in list(aliases):
        if key.startswith("novel.setup."):
            aliases.add(key.removeprefix("novel.setup."))
        if key.startswith("novel."):
            short = key.removeprefix("novel.")
            aliases.add(short)
            aliases.add(f"novel_{short}")
    aliases.discard("")
    return aliases


def _prompt_value_for_render(raw_value: Any, rendered_value: Any) -> Any:
    if isinstance(raw_value, (Mapping, list, tuple)):
        return PromptValueView(raw_value, rendered_value)
    if raw_value is rendered_value:
        return rendered_value
    return rendered_value


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


def aliases_with_binding_variable_keys(
    aliases: Mapping[str, Any],
    bindings: list[VariableBinding] | tuple[VariableBinding, ...],
    raw_aliases: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expanded: dict[str, Any] = dict(aliases or {})
    raw_aliases = raw_aliases or {}
    for alias, value in list(expanded.items()):
        if alias in raw_aliases:
            expanded[alias] = _prompt_value_for_render(raw_aliases[alias], value)
    for binding in bindings or ():
        if not binding.enabled or not binding.variable_key or binding.alias not in aliases:
            continue
        expanded[str(binding.variable_key)] = _prompt_value_for_render(
            raw_aliases.get(binding.alias, aliases[binding.alias]),
            aliases[binding.alias],
        )
    return expanded


def build_prompt_render_variables(
    aliases: Mapping[str, Any],
    bindings: list[VariableBinding] | tuple[VariableBinding, ...],
    raw_aliases: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return aliases_with_dotted_variables(
        aliases_with_binding_variable_keys(aliases, bindings, raw_aliases)
    )


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
    public_bound_aliases = {
        alias
        for binding in bindings
        for alias in public_aliases_for_binding(binding)
    }
    added = []
    for variable_key in sorted(declared_keys):
        variable_key = normalize_declared_variable_reference(
            variable_key,
            bound_variable_keys | bound_aliases | public_bound_aliases,
        )
        if is_reference_to_existing_binding(variable_key, bindings):
            continue
        if variable_key in bound_variable_keys or variable_key in bound_aliases or variable_key in public_bound_aliases:
            continue
        alias = alias_for_variable_key(variable_key)
        if alias in bound_aliases:
            suffix = 2
            base = alias_for_variable_key(variable_key)
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
        public_bound_aliases.add(alias)
        added.append({"alias": alias, "variable_key": variable_key})
    return bindings, added
