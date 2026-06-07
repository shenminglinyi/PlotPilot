"""Runtime prompt context providers.

Some CPMS templates need deterministic system-built values, such as schema
snippets, that are not author-editable Variable Hub facts. Providers registered
here inject those values at render time only; they are intentionally absent
from input bindings, missing-variable review, and Variable Hub snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from application.ai_invocation.dtos import InvocationSpec


@dataclass(frozen=True)
class RuntimePromptContext:
    spec: InvocationSpec
    aliases: Mapping[str, Any]


RuntimePromptProvider = Callable[[RuntimePromptContext], Mapping[str, Any]]

_PROVIDERS: dict[tuple[str, str], RuntimePromptProvider] = {}


def register_runtime_prompt_provider(
    *,
    operation: str,
    node_key: str,
    provider: RuntimePromptProvider,
) -> None:
    _PROVIDERS[(operation, node_key)] = provider


def runtime_prompt_values_for_spec(
    spec: InvocationSpec,
    aliases: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    provider = _PROVIDERS.get((spec.operation, spec.node_key))
    if provider is None:
        provider = _PROVIDERS.get(("", spec.node_key))
    if provider is None:
        return {}
    return dict(provider(RuntimePromptContext(spec=spec, aliases=aliases or {})) or {})


def runtime_prompt_value_names_for_spec(spec: InvocationSpec) -> set[str]:
    return set(runtime_prompt_values_for_spec(spec, {}).keys())


def with_runtime_prompt_values(
    spec: InvocationSpec,
    aliases: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(aliases or {})
    for alias, value in runtime_prompt_values_for_spec(spec, merged).items():
        merged.setdefault(alias, value)
    return merged


def _bible_worldbuilding_runtime_values(_context: RuntimePromptContext) -> Mapping[str, Any]:
    from application.world.worldbuilding_schema import build_fields_desc_for_prompt

    return {
        "fields_desc": build_fields_desc_for_prompt(),
        "genre_opening_profile": {},
        "genre_reader_contract": {},
        "genre_rhythm_constraints": {},
    }


register_runtime_prompt_provider(
    operation="bible.setup.worldbuilding",
    node_key="bible-worldbuilding",
    provider=_bible_worldbuilding_runtime_values,
)
