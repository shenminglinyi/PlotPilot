"""Persist invocation input variables into Variable Hub."""
from __future__ import annotations

from typing import Any, Mapping

from application.ai_invocation.dtos import InvocationSession, InvocationSpec, VariableBinding, VariablePlan
from application.ai_invocation.variable_hub import VariableHubRepository, VariableWrite


def context_key_for_scope(context: Mapping[str, Any], scope: str = "") -> str:
    novel_id = str(context.get("novel_id") or "").strip()
    chapter_number = context.get("chapter_number")
    beat_index = context.get("beat_index")
    normalized_scope = str(scope or "").strip().lower()
    if normalized_scope == "beat" and novel_id and chapter_number not in (None, "") and beat_index not in (None, ""):
        return f"novel_id:{novel_id}|chapter_number:{chapter_number}|beat_index:{beat_index}"
    if normalized_scope in {"beat", "chapter", "scene"} and novel_id and chapter_number not in (None, ""):
        return f"novel_id:{novel_id}|chapter_number:{chapter_number}"
    if novel_id:
        return f"novel_id:{novel_id}"
    return "global"


def materialize_input_variables(
    *,
    variable_hub_repository: VariableHubRepository,
    session: InvocationSession,
    spec: InvocationSpec,
    variable_plan: VariablePlan | None,
    extra_bindings: list[VariableBinding] | None = None,
    updated_by: str = "system",
) -> dict[str, Any]:
    if variable_plan is None:
        return {"skipped": True, "reason": "missing_variable_plan"}

    bindings = [
        *variable_hub_repository.get_bindings(spec.input_binding_set_id, spec.node_key),
        *(extra_bindings or []),
    ]
    binding_by_alias = {binding.alias: binding for binding in bindings if binding.enabled}
    written: list[dict[str, Any]] = []
    for alias, value in dict(variable_plan.aliases or {}).items():
        binding = binding_by_alias.get(alias)
        if binding is None or not binding.variable_key:
            continue
        context_key = context_key_for_scope(session.context, binding.scope)
        stored = variable_hub_repository.set_value(
            VariableWrite(
                key=binding.variable_key,
                value=value,
                context_key=context_key,
                source_session_id=session.id,
                source_trace_id=str((session.metadata or {}).get("trace_id") or session.id),
                source_node_key=session.node_key,
                lineage={
                    "alias": alias,
                    "binding_set_id": spec.input_binding_set_id,
                    "operation": session.operation,
                    "phase": "input_materialized",
                    "updated_by": updated_by,
                },
                value_type=binding.value_type,
                display_name=binding.display_name,
                scope=binding.scope,
                stage=binding.stage,
            )
        )
        written.append(
            {
                "alias": alias,
                "variable_key": binding.variable_key,
                "context_key": context_key,
                "version_number": getattr(stored, "version_number", 1),
            }
        )

    if not written:
        return {"skipped": True, "reason": "no_materializable_inputs"}

    metadata = dict(session.metadata or {})
    metadata["input_variable_materialization"] = {"updated_by": updated_by, "written": written}
    session.metadata = metadata
    return {
        "skipped": False,
        "written": written,
        "binding_set_id": spec.input_binding_set_id,
    }
