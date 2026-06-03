"""AI Invocation API.

该路由只暴露统一 AI 调用会话，不在接口层拼接 prompt 或直接访问业务表。
"""
from __future__ import annotations

import json
import asyncio
import logging
import time
import uuid
from typing import Any, Mapping
from dataclasses import replace

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from application.ai_invocation.dtos import (
    InvocationAttempt,
    InvocationAttemptStatus,
    InvocationPolicy,
    InvocationRequest,
    InvocationSessionStatus,
    VariableBinding,
    prompt_hash,
    stable_hash,
)
from application.ai_invocation.gateway import AIInvocationGateway
from application.ai_invocation.input_materialization import context_key_for_scope, materialize_input_variables
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler, PromptAssemblyError
from application.ai_invocation.prompt_variables import (
    aliases_with_binding_variable_keys,
    aliases_with_dotted_variables,
    prompt_declared_input_bindings,
)
from application.ai_invocation.services import AdoptionCommitService, AdoptionService, AttemptService, InvocationSessionService
from application.ai_invocation.spec_service import InvocationSpecNotFoundError, InvocationSpecService
from application.ai_invocation.variable_hub import RUNTIME_ONLY_BINDING_SOURCES, VariableResolver, VariableWrite
from application.ai_invocation.variable_hub_context import (
    format_setup_variable_hub_context,
    inject_setup_variable_hub_context,
)
from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
    SqliteAdoptionRepository,
    SqliteInvocationAttemptRepository,
    SqliteInvocationSessionRepository,
    SqliteInvocationSpecRepository,
    SqliteVariableHubRepository,
    prompt_snapshot_to_dict,
    variable_plan_to_dict,
)
from interfaces.api.dependencies import get_llm_service

logger = logging.getLogger(__name__)

try:
    from application.ai_invocation.autopilot.continuations import register_autopilot_continuations
    from application.ai_invocation.contracts.chapter_prose_generation import register_chapter_prose_generation_continuation
    from application.blueprint.services.setup_main_plot_continuation import register_setup_main_plot_continuation
    from application.world.services.bible_setup_continuation import register_bible_setup_continuations

    register_autopilot_continuations()
    register_chapter_prose_generation_continuation()
    register_setup_main_plot_continuation()
    register_bible_setup_continuations()
except Exception:
    pass


router = APIRouter(prefix="/ai-invocations", tags=["ai-invocation"])


class InvocationCreateRequest(BaseModel):
    operation: str
    node_key: str
    variables: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    policy: InvocationPolicy | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdoptionAcceptRequest(BaseModel):
    attempt_id: str
    accepted_by: str = "user"
    commit_prompt_version: bool = False
    commit_variable_outputs: bool = False
    commit_variable_bindings: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommitCreateRequest(BaseModel):
    decision_id: str


class ResumeInvocationRequest(BaseModel):
    resumed_by: str = "user"
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptDraftRequest(BaseModel):
    system_template: str = ""
    user_template: str | None = None


class VariableUpdateRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    updated_by: str = "user"


def _config_from_dict(raw: Mapping[str, Any] | None) -> GenerationConfig | None:
    if not raw:
        return None
    max_tokens = int(raw.get("max_tokens") or 4096)
    operation = str(raw.get("operation") or raw.get("invocation_operation") or "")
    if operation == "setup.main_plot_options":
        max_tokens = max(max_tokens, 8192)
    return GenerationConfig(
        model=str(raw.get("model") or ""),
        max_tokens=max_tokens,
        temperature=float(raw.get("temperature") if raw.get("temperature") is not None else 1.0),
        response_format=raw.get("response_format"),
    )


def _repositories():
    db = get_database()
    return {
        "spec": SqliteInvocationSpecRepository(db),
        "variable_hub": SqliteVariableHubRepository(db),
        "session": SqliteInvocationSessionRepository(db),
        "attempt": SqliteInvocationAttemptRepository(db),
        "adoption": SqliteAdoptionRepository(db),
    }


def _save_invocation_result(repos, result) -> None:
    """同步保存一次 invocation 结果。

    AI Invocation 是交互态：创建后前端会立即按 session_id 查询。
    这里必须避免普通 API 线程写入持久化队列后产生读后写不可见。
    """
    with sqlite_writes_bypass_queue():
        repos["session"].save(result.session)
        if result.attempt is not None:
            repos["attempt"].save(result.attempt)
        if result.decision is not None:
            repos["adoption"].save_decision(result.decision)
        if result.commit is not None:
            repos["adoption"].save_commit(result.commit)


def _publish_autopilot_session_state(session) -> None:
    operation = str(getattr(session, "operation", "") or "")
    if not operation.startswith("autopilot."):
        return
    metadata = dict(getattr(session, "metadata", {}) or {})
    context = dict(getattr(session, "context", {}) or {})
    novel_id = str(metadata.get("novel_id") or context.get("novel_id") or "").strip()
    if not novel_id:
        return

    from application.ai_invocation.autopilot.publisher import AutopilotSessionPublisher

    status_value = session.status.value if hasattr(session.status, "value") else str(session.status)
    awaiting = session.status in {
        InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
        InvocationSessionStatus.AWAITING_ACCEPTANCE,
        InvocationSessionStatus.AWAITING_COMMIT,
        InvocationSessionStatus.BLOCKED,
        InvocationSessionStatus.FAILED,
        InvocationSessionStatus.CANCELLED,
    }
    if session.status == InvocationSessionStatus.COMPLETED:
        payload = {
            "active_invocation_session_id": session.id,
            "active_invocation_operation": session.operation,
            "active_invocation_node_key": session.node_key,
            "active_invocation_status": status_value,
            "active_invocation_policy": session.policy.value if hasattr(session.policy, "value") else str(session.policy),
            "has_active_invocation": False,
            "requires_ai_review": False,
            "autopilot_pause_reason": "",
        }
    else:
        payload = {
            "active_invocation_session_id": session.id,
            "active_invocation_operation": session.operation,
            "active_invocation_node_key": session.node_key,
            "active_invocation_status": status_value,
            "active_invocation_policy": session.policy.value if hasattr(session.policy, "value") else str(session.policy),
            "has_active_invocation": True,
            "requires_ai_review": awaiting,
            "autopilot_pause_reason": (
                "ai_invocation_retry_required"
                if session.status in {InvocationSessionStatus.FAILED, InvocationSessionStatus.CANCELLED}
                else ("awaiting_ai_review" if awaiting else "")
            ),
        }
    AutopilotSessionPublisher().publish(novel_id, payload)


def _session_payload(session) -> dict[str, Any]:
    return {
        "id": session.id,
        "operation": session.operation,
        "node_key": session.node_key,
        "policy": session.policy.value if hasattr(session.policy, "value") else str(session.policy),
        "status": session.status.value if hasattr(session.status, "value") else str(session.status),
        "context": dict(session.context or {}),
        "metadata": dict(session.metadata or {}),
        "attempts": list(session.attempts or []),
        "prompt_snapshot": prompt_snapshot_to_dict(session.prompt_snapshot),
        "variable_plan": variable_plan_to_dict(session.variable_plan),
    }


def _attempt_payload(attempt) -> dict[str, Any] | None:
    if attempt is None:
        return None
    return {
        "id": attempt.id,
        "session_id": attempt.session_id,
        "status": attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status),
        "content": attempt.content,
        "error": attempt.error,
    }


def _decision_payload(decision) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "id": decision.id,
        "session_id": decision.session_id,
        "attempt_id": decision.attempt_id,
        "decision": decision.decision,
        "accept_content": decision.accept_content,
        "commit_prompt_version": decision.commit_prompt_version,
        "commit_variable_outputs": decision.commit_variable_outputs,
        "commit_variable_bindings": decision.commit_variable_bindings,
    }


def _commit_payload(commit) -> dict[str, Any] | None:
    if commit is None:
        return None
    return {
        "id": commit.id,
        "session_id": commit.session_id,
        "decision_id": commit.decision_id,
        "status": commit.status.value if hasattr(commit.status, "value") else str(commit.status),
        "steps": [
            {
                "name": step.name,
                "status": step.status.value if hasattr(step.status, "value") else str(step.status),
                "result": dict(step.result or {}),
                "error": step.error,
            }
            for step in commit.steps
        ],
        "result": dict(commit.result or {}),
        "error": commit.error,
    }


def _safe_json_loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _binding_to_metadata(binding: VariableBinding) -> dict[str, Any]:
    return {
        "alias": binding.alias,
        "variable_key": binding.variable_key,
        "required": binding.required,
        "default": binding.default,
        "source": binding.source,
        "enabled": binding.enabled,
        "value_type": binding.value_type,
        "scope": binding.scope,
        "stage": binding.stage,
        "display_name": binding.display_name,
    }


def _binding_from_metadata(raw: Mapping[str, Any]) -> VariableBinding:
    return VariableBinding(
        alias=str(raw.get("alias") or ""),
        variable_key=str(raw.get("variable_key") or ""),
        required=bool(raw.get("required")),
        default=raw.get("default"),
        source=str(raw.get("source") or ""),
        enabled=bool(raw.get("enabled", True)),
        value_type=str(raw.get("value_type") or "string"),
        scope=str(raw.get("scope") or "runtime"),
        stage=str(raw.get("stage") or "runtime"),
        display_name=str(raw.get("display_name") or raw.get("variable_key") or raw.get("alias") or ""),
    )


def _session_prompt_declared_bindings(session) -> list[VariableBinding]:
    raw_items = (session.metadata or {}).get("prompt_declared_input_bindings") or []
    if not isinstance(raw_items, list):
        return []
    bindings: list[VariableBinding] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        binding = _binding_from_metadata(raw)
        if binding.alias and binding.variable_key:
            bindings.append(binding)
    return bindings


def _session_input_bindings(repos, session, spec) -> list[VariableBinding]:
    base_bindings = repos["variable_hub"].get_bindings(spec.input_binding_set_id, spec.node_key)
    base_keys = {(binding.alias, binding.variable_key) for binding in base_bindings}
    extra_bindings = [
        binding
        for binding in _session_prompt_declared_bindings(session)
        if (binding.alias, binding.variable_key) not in base_keys
    ]
    return [*base_bindings, *extra_bindings]


class _SessionBindingVariableHubRepository:
    def __init__(self, base_repository, *, input_binding_set_id: str, node_key: str, input_bindings: list[VariableBinding]):
        self._base_repository = base_repository
        self._input_binding_set_id = input_binding_set_id
        self._node_key = node_key
        self._input_bindings = list(input_bindings)

    def get_bindings(self, binding_set_id: str, node_key: str) -> list[VariableBinding]:
        if binding_set_id == self._input_binding_set_id and node_key == self._node_key:
            return list(self._input_bindings)
        return self._base_repository.get_bindings(binding_set_id, node_key)

    def get_output_bindings(self, binding_set_id: str, node_key: str):
        return self._base_repository.get_output_bindings(binding_set_id, node_key)

    def get_value(self, variable_key: str, context_key: str):
        return self._base_repository.get_value(variable_key, context_key)

    def get_definition(self, variable_key: str):
        return self._base_repository.get_definition(variable_key)

    def list_current_values(self, context_key: str):
        return self._base_repository.list_current_values(context_key)

    def set_value(self, value):
        return self._base_repository.set_value(value)

    def set_bindings(self, binding_set_id: str, node_key: str, bindings: list[VariableBinding], *, direction: str = "input") -> None:
        self._base_repository.set_bindings(binding_set_id, node_key, bindings, direction=direction)


def _session_variable_resolver(repos, session, spec) -> VariableResolver:
    return VariableResolver(
        _SessionBindingVariableHubRepository(
            repos["variable_hub"],
            input_binding_set_id=spec.input_binding_set_id,
            node_key=spec.node_key,
            input_bindings=_session_input_bindings(repos, session, spec),
        )
    )


def _runtime_only_explicit_variables(session, bindings: list[VariableBinding]) -> dict[str, Any]:
    aliases = dict(getattr(getattr(session, "variable_plan", None), "aliases", {}) or {})
    if not aliases:
        return {}
    runtime_aliases = {
        binding.alias
        for binding in bindings
        if binding.source in RUNTIME_ONLY_BINDING_SOURCES
        or (binding.variable_key and str(binding.variable_key).startswith("system."))
    }
    return {alias: aliases[alias] for alias in runtime_aliases if alias in aliases}


def _resolve_current_variable_plan(repos, session, spec=None):
    spec = spec or repos["spec"].get(session.operation, session.node_key)
    if spec is None:
        return session.variable_plan
    input_bindings = _session_input_bindings(repos, session, spec)
    return _session_variable_resolver(repos, session, spec).resolve(
        spec=spec,
        explicit_variables=_runtime_only_explicit_variables(session, input_bindings),
        context=session.context,
    )


def _refresh_session_variables_from_hub(repos, session, *, render_prompt: bool = False, persist: bool = False):
    spec = repos["spec"].get(session.operation, session.node_key)
    if spec is None:
        return session
    variable_plan = _resolve_current_variable_plan(repos, session, spec)
    session.variable_plan = variable_plan
    if render_prompt and session.prompt_snapshot is not None:
        draft_prompt = session.prompt_snapshot.draft_prompt
        template_prompt = session.prompt_snapshot.template_prompt
        if draft_prompt is not None:
            session.prompt_snapshot = _render_prompt_draft(session, draft_prompt.system, draft_prompt.user)
        elif template_prompt is not None:
            session.prompt_snapshot = _render_prompt_draft(session, template_prompt.system, template_prompt.user)
        else:
            session.prompt_snapshot = CPMSPromptAssembler().compile(spec=spec, variable_plan=variable_plan)
    if persist:
        with sqlite_writes_bypass_queue():
            repos["session"].save(session)
    return session


def _sync_prompt_declared_input_bindings(repos, session, spec, system_template: str, user_template: str) -> None:
    base_bindings = repos["variable_hub"].get_bindings(spec.input_binding_set_id, spec.node_key)
    bindings, added = prompt_declared_input_bindings(
        existing_bindings=base_bindings,
        system_template=system_template,
        user_template=user_template,
    )
    metadata = dict(session.metadata or {})
    prompt_declared_bindings = [binding for binding in bindings if binding.source == "prompt_draft"]
    metadata["prompt_declared_variables"] = [
        {"alias": binding.alias, "variable_key": binding.variable_key}
        for binding in prompt_declared_bindings
    ]
    metadata["prompt_declared_input_bindings"] = [
        _binding_to_metadata(binding)
        for binding in prompt_declared_bindings
    ]
    metadata["last_prompt_declared_variables_added"] = added
    session.metadata = metadata


def _is_prompt_draft_editable(session) -> bool:
    if session.status == InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW:
        return True
    if session.status == InvocationSessionStatus.BLOCKED and not (session.attempts or ()):
        return True
    return False


def _load_related_payloads(repos, session_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    session = repos["session"].get(session_id)
    if session is None:
        return None, None, None

    attempt_payload = None
    latest_attempt = None
    if session.attempts:
        latest_attempt = repos["attempt"].get(session.attempts[-1])
        attempt_payload = _attempt_payload(latest_attempt)

    decision_payload = None
    commit_payload = None
    if latest_attempt is not None:
        decision = repos["adoption"].get_latest_decision_for_attempt(session_id, latest_attempt.id)
        if decision is not None:
            decision_payload = _decision_payload(decision)
            commit = repos["adoption"].get_commit_for_decision(decision.id)
            if commit is not None:
                commit_payload = _commit_payload(commit)

    return attempt_payload, decision_payload, commit_payload


async def _run_streaming_invocation_attempt(
    *,
    session_id: str,
    attempt_id: str,
    config: GenerationConfig | None,
) -> None:
    """Run the LLM call outside the request lifecycle and persist streaming text.

    The review panel polls the session while this task is running. This keeps
    `/resume` fast and avoids frontend HTTP timeouts for long generations.
    """
    repos = _repositories()
    session = repos["session"].get(session_id)
    attempt = repos["attempt"].get(attempt_id)
    if session is None or attempt is None or session.prompt_snapshot is None:
        logger.warning(
            "streaming invocation aborted: session=%s attempt=%s missing persisted state",
            session_id,
            attempt_id,
        )
        return

    llm_service = get_llm_service()
    parts: list[str] = []
    last_save = 0.0
    try:
        async for chunk in llm_service.stream_generate(
            session.prompt_snapshot.prompt,
            config or GenerationConfig(),
        ):
            if not chunk:
                continue
            parts.append(chunk)
            now = time.monotonic()
            if now - last_save >= 0.35:
                attempt.content = "".join(parts)
                with sqlite_writes_bypass_queue():
                    repos["attempt"].save(attempt)
                last_save = now

        attempt.content = "".join(parts)
        if not attempt.content.strip():
            raise ValueError("Content cannot be empty")
        attempt.status = InvocationAttemptStatus.SUCCEEDED
        session.status = InvocationSessionStatus.AWAITING_ACCEPTANCE
        with sqlite_writes_bypass_queue():
            repos["attempt"].save(attempt)
            repos["session"].save(session)
        _publish_autopilot_session_state(session)
    except Exception as exc:
        attempt.content = "".join(parts)
        attempt.status = InvocationAttemptStatus.FAILED
        attempt.error = str(exc)
        session.status = InvocationSessionStatus.FAILED
        with sqlite_writes_bypass_queue():
            repos["attempt"].save(attempt)
            repos["session"].save(session)
        _publish_autopilot_session_state(session)
        logger.exception(
            "streaming invocation failed: session=%s attempt=%s",
            session_id,
            attempt_id,
        )


def _render_prompt_draft(session, system_template: str, user_template: str | None = None):
    if session.prompt_snapshot is None:
        raise HTTPException(status_code=400, detail="invocation_session_missing_prompt_snapshot")
    if session.variable_plan is None:
        raise HTTPException(status_code=400, detail="invocation_session_missing_variable_plan")
    from infrastructure.ai.prompt_template_engine import get_template_engine

    effective_user_template = (
        user_template
        if user_template is not None
        else (
            session.prompt_snapshot.template_prompt.user
            if session.prompt_snapshot.template_prompt is not None
            else ""
        )
    )

    render_aliases = aliases_with_binding_variable_keys(
        session.variable_plan.aliases or {},
        session.variable_plan.bindings,
    )
    for item in session.variable_plan.snapshot_items or ():
        if isinstance(item, Mapping) and item.get("variable_key"):
            render_aliases.setdefault(str(item.get("variable_key")), item.get("value"))
    variable_hub_context = format_setup_variable_hub_context(session.variable_plan.snapshot_items)
    render_aliases["variable_hub_context"] = variable_hub_context

    render_result = get_template_engine().render(
        system_template=system_template,
        user_template=effective_user_template,
        variables=aliases_with_dotted_variables(render_aliases),
    )
    prompt = Prompt(
        system=render_result.system or "",
        user=inject_setup_variable_hub_context(render_result.user or "", variable_hub_context),
    )
    base_template_prompt = (
        session.prompt_snapshot.template_prompt
        if session.prompt_snapshot.template_prompt is not None
        else Prompt(system=system_template, user=effective_user_template)
    )
    draft_prompt = Prompt(
        system=system_template,
        user=effective_user_template,
    )
    diagnostics = list(session.variable_plan.diagnostics or ())
    if getattr(render_result, "warnings", None):
        diagnostics.extend(str(item) for item in render_result.warnings)
    if getattr(render_result, "errors", None):
        diagnostics.extend(str(item) for item in render_result.errors)
    if session.variable_plan.required_missing:
        diagnostics.append("存在未解析的必填变量")

    snapshot = replace(
        session.prompt_snapshot,
        prompt=prompt,
        template_prompt=base_template_prompt,
        draft_prompt=draft_prompt,
        template_hash=stable_hash(
            {
                "system_template": draft_prompt.system,
                "user_template": draft_prompt.user,
            }
        ),
        rendered_prompt_hash=prompt_hash(prompt),
        missing_variables=tuple(getattr(render_result, "missing_variables", []) or ()),
        diagnostics=tuple(diagnostics),
    )
    return snapshot


@router.post("")
async def create_invocation(request: InvocationCreateRequest) -> dict[str, Any]:
    repos = _repositories()
    try:
        from application.ai_invocation.contracts import ensure_invocation_contract

        ensure_invocation_contract(request.operation, request.node_key, get_database())
    except ValueError:
        pass
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    llm_service = get_llm_service()
    gateway = AIInvocationGateway(
        spec_service=InvocationSpecService(repos["spec"]),
        variable_resolver=VariableResolver(repos["variable_hub"]),
        prompt_assembler=CPMSPromptAssembler(),
        llm_service=llm_service,
        session_service=InvocationSessionService(),
        attempt_service=AttemptService(llm_service),
        adoption_service=AdoptionService(),
        commit_service=AdoptionCommitService(variable_hub_repository=repos["variable_hub"]),
    )
    try:
        result = await gateway.invoke(
            InvocationRequest(
                operation=request.operation,
                node_key=request.node_key,
                variables=request.variables,
                context=request.context,
                policy=request.policy,
                config=_config_from_dict(request.config),
                metadata=request.metadata,
            )
        )
    except InvocationSpecNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PromptAssemblyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    spec = repos["spec"].get(result.session.operation, result.session.node_key)
    if spec is not None:
        materialize_input_variables(
            variable_hub_repository=repos["variable_hub"],
            session=result.session,
            spec=spec,
            variable_plan=result.variable_plan,
            updated_by="create_invocation",
        )

    _save_invocation_result(repos, result)
    _publish_autopilot_session_state(result.session)

    return {
        "session": _session_payload(result.session),
        "attempt": _attempt_payload(result.attempt),
        "decision": _decision_payload(result.decision),
        "commit": _commit_payload(result.commit),
        "next_action": _next_action(result.session.status),
    }


@router.get("/{session_id}")
async def get_invocation(session_id: str) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    _refresh_session_variables_from_hub(
        repos,
        session,
        render_prompt=session.status in {InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW, InvocationSessionStatus.BLOCKED},
        persist=False,
    )
    attempt_payload, decision_payload, commit_payload = _load_related_payloads(repos, session_id)
    return {
        "session": _session_payload(session),
        "attempt": attempt_payload,
        "decision": decision_payload,
        "commit": commit_payload,
        "next_action": _next_action(session.status),
    }


@router.post("/{session_id}/prompt-draft/preview")
async def preview_prompt_draft(session_id: str, request: PromptDraftRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    spec = repos["spec"].get(session.operation, session.node_key)
    if spec is not None:
        _sync_prompt_declared_input_bindings(
            repos,
            session,
            spec,
            request.system_template,
            request.user_template
            if request.user_template is not None
            else (
                session.prompt_snapshot.template_prompt.user
                if session.prompt_snapshot and session.prompt_snapshot.template_prompt
                else ""
            ),
        )
        variable_plan = _session_variable_resolver(repos, session, spec).resolve(spec=spec, explicit_variables={}, context=session.context)
        session.variable_plan = variable_plan
    snapshot = _render_prompt_draft(session, request.system_template, request.user_template)
    return {
        "prompt_snapshot": prompt_snapshot_to_dict(snapshot),
        "variable_plan": variable_plan_to_dict(session.variable_plan),
    }


@router.put("/{session_id}/prompt-draft")
async def save_prompt_draft(session_id: str, request: PromptDraftRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    if not _is_prompt_draft_editable(session):
        raise HTTPException(status_code=400, detail="invocation_session_not_waiting_for_pre_call_review")
    spec = repos["spec"].get(session.operation, session.node_key)
    if spec is not None:
        _sync_prompt_declared_input_bindings(
            repos,
            session,
            spec,
            request.system_template,
            request.user_template
            if request.user_template is not None
            else (
                session.prompt_snapshot.template_prompt.user
                if session.prompt_snapshot and session.prompt_snapshot.template_prompt
                else ""
            ),
        )
        variable_plan = _session_variable_resolver(repos, session, spec).resolve(spec=spec, explicit_variables={}, context=session.context)
        session.variable_plan = variable_plan
    session.prompt_snapshot = _render_prompt_draft(session, request.system_template, request.user_template)
    session.status = (
        InvocationSessionStatus.BLOCKED
        if session.variable_plan is not None and not session.variable_plan.ok
        else InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW
    )
    with sqlite_writes_bypass_queue():
        repos["session"].save(session)
    return {
        "session": _session_payload(session),
        "next_action": _next_action(session.status),
    }


@router.put("/{session_id}/variables")
async def update_invocation_variables(session_id: str, request: VariableUpdateRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    if session.status not in {
        InvocationSessionStatus.BLOCKED,
        InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
        InvocationSessionStatus.VARIABLES_RESOLVED,
        InvocationSessionStatus.PROMPT_COMPILED,
    }:
        raise HTTPException(status_code=400, detail="invocation_session_variables_not_editable")

    spec = repos["spec"].get(session.operation, session.node_key)
    if spec is None:
        raise HTTPException(status_code=404, detail="invocation_spec_not_found")
    bindings = {
        binding.alias: binding
        for binding in _session_input_bindings(repos, session, spec)
        if binding.enabled
    }
    if not request.values:
        raise HTTPException(status_code=400, detail="variable_values_required")

    written: list[dict[str, Any]] = []
    for alias, value in request.values.items():
        binding = bindings.get(alias)
        if binding is None:
            for item in bindings.values():
                if item.variable_key == alias:
                    binding = item
                    break
        if binding is None:
            raise HTTPException(status_code=400, detail=f"variable_binding_not_found:{alias}")
        if not binding.variable_key:
            raise HTTPException(status_code=400, detail=f"variable_key_not_bound:{alias}")
        if binding.source in RUNTIME_ONLY_BINDING_SOURCES or str(binding.variable_key).startswith("system."):
            raise HTTPException(status_code=400, detail=f"variable_not_persistable:{alias}")
        stored = repos["variable_hub"].set_value(
            VariableWrite(
                key=binding.variable_key,
                value=value,
                context_key=context_key_for_scope(session.context, binding.scope),
                source_session_id=session.id,
                source_trace_id=str(session.metadata.get("trace_id") or session.id),
                source_node_key=session.node_key,
                lineage={
                    "alias": alias,
                    "binding_set_id": spec.input_binding_set_id,
                    "operation": session.operation,
                    "updated_by": request.updated_by,
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
                "context_key": context_key_for_scope(session.context, binding.scope),
                "version_number": getattr(stored, "version_number", 1),
            }
        )

    resolver = _session_variable_resolver(repos, session, spec)
    variable_plan = resolver.resolve(spec=spec, explicit_variables={}, context=session.context)
    session.variable_plan = variable_plan
    draft_prompt = session.prompt_snapshot.draft_prompt if session.prompt_snapshot is not None else None
    if draft_prompt is not None:
        prompt_snapshot = _render_prompt_draft(session, draft_prompt.system, draft_prompt.user)
    else:
        try:
            prompt_snapshot = CPMSPromptAssembler().compile(spec=spec, variable_plan=variable_plan)
        except PromptAssemblyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.prompt_snapshot = prompt_snapshot
    session.status = (
        InvocationSessionStatus.BLOCKED
        if not variable_plan.ok
        else InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW
    )
    metadata = dict(session.metadata or {})
    metadata["last_variable_update"] = {"updated_by": request.updated_by, "written": written}
    session.metadata = metadata
    with sqlite_writes_bypass_queue():
        repos["session"].save(session)
    _publish_autopilot_session_state(session)
    return {
        "session": _session_payload(session),
        "next_action": _next_action(session.status),
        "variable_writes": written,
    }


@router.post("/{session_id}/accept")
async def accept_invocation(session_id: str, request: AdoptionAcceptRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    attempt = repos["attempt"].get(request.attempt_id)
    if attempt is None or attempt.session_id != session_id:
        raise HTTPException(status_code=404, detail="invocation_attempt_not_found")

    decision = AdoptionService().accept(
        session=session,
        attempt=attempt,
        accepted_by=request.accepted_by,
        commit_prompt_version=request.commit_prompt_version,
        commit_variable_outputs=request.commit_variable_outputs,
        commit_variable_bindings=request.commit_variable_bindings,
        metadata=request.metadata,
    )
    with sqlite_writes_bypass_queue():
        repos["adoption"].save_decision(decision)
        repos["session"].save(session)
    _publish_autopilot_session_state(session)
    return {
        "session": _session_payload(session),
        "decision": _decision_payload(decision),
        "next_action": "commit_required",
    }


@router.post("/{session_id}/resume")
async def resume_invocation(session_id: str, request: ResumeInvocationRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    if session.status != InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW:
        raise HTTPException(status_code=400, detail="invocation_session_not_waiting_for_pre_call_review")
    if session.prompt_snapshot is None:
        raise HTTPException(status_code=400, detail="invocation_session_missing_prompt_snapshot")
    _refresh_session_variables_from_hub(repos, session, render_prompt=True, persist=False)
    if session.variable_plan is not None and not session.variable_plan.ok:
        session.status = InvocationSessionStatus.BLOCKED
        with sqlite_writes_bypass_queue():
            repos["session"].save(session)
        return {
            "session": _session_payload(session),
            "next_action": _next_action(session.status),
        }

    attempt = InvocationAttempt(
        id=str(uuid.uuid4()),
        session_id=session.id,
        status=InvocationAttemptStatus.RUNNING,
        prompt_snapshot=session.prompt_snapshot,
    )
    session.attempts.append(attempt.id)
    session.status = InvocationSessionStatus.GENERATING
    with sqlite_writes_bypass_queue():
        repos["attempt"].save(attempt)
        repos["session"].save(session)
    _publish_autopilot_session_state(session)
    asyncio.create_task(
        _run_streaming_invocation_attempt(
            session_id=session.id,
            attempt_id=attempt.id,
            config=_config_from_dict({**request.config, "operation": session.operation}),
        )
    )
    return {
        "session": _session_payload(session),
        "attempt": _attempt_payload(attempt),
        "next_action": "generating",
    }


@router.post("/{session_id}/retry")
async def retry_invocation(session_id: str, request: ResumeInvocationRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    if session.prompt_snapshot is None:
        raise HTTPException(status_code=400, detail="invocation_session_missing_prompt_snapshot")
    if session.status not in {
        InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
        InvocationSessionStatus.AWAITING_ACCEPTANCE,
        InvocationSessionStatus.CANCELLED,
        InvocationSessionStatus.FAILED,
    }:
        raise HTTPException(status_code=400, detail="invocation_session_not_retryable")
    _refresh_session_variables_from_hub(repos, session, render_prompt=True, persist=False)
    if session.variable_plan is not None and not session.variable_plan.ok:
        session.status = InvocationSessionStatus.BLOCKED
        with sqlite_writes_bypass_queue():
            repos["session"].save(session)
        return {
            "session": _session_payload(session),
            "next_action": _next_action(session.status),
        }

    attempt = InvocationAttempt(
        id=str(uuid.uuid4()),
        session_id=session.id,
        status=InvocationAttemptStatus.RUNNING,
        prompt_snapshot=session.prompt_snapshot,
    )
    session.attempts.append(attempt.id)
    session.status = InvocationSessionStatus.GENERATING
    with sqlite_writes_bypass_queue():
        repos["attempt"].save(attempt)
        repos["session"].save(session)
    _publish_autopilot_session_state(session)
    asyncio.create_task(
        _run_streaming_invocation_attempt(
            session_id=session.id,
            attempt_id=attempt.id,
            config=_config_from_dict({**request.config, "operation": session.operation}),
        )
    )
    return {
        "session": _session_payload(session),
        "attempt": _attempt_payload(attempt),
        "next_action": "generating",
    }


@router.post("/{session_id}/reject")
async def reject_invocation(session_id: str, request: AdoptionAcceptRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    attempt = repos["attempt"].get(request.attempt_id)
    if attempt is None or attempt.session_id != session_id:
        raise HTTPException(status_code=404, detail="invocation_attempt_not_found")
    decision = AdoptionService().reject(session=session, attempt=attempt, accepted_by=request.accepted_by)
    with sqlite_writes_bypass_queue():
        repos["adoption"].save_decision(decision)
        repos["session"].save(session)
    _publish_autopilot_session_state(session)
    return {
        "session": _session_payload(session),
        "decision": _decision_payload(decision),
        "next_action": "cancelled",
    }


@router.post("/{session_id}/commits")
async def create_commit(session_id: str, request: CommitCreateRequest) -> dict[str, Any]:
    repos = _repositories()
    session = repos["session"].get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="invocation_session_not_found")
    decision = repos["adoption"].get_decision(request.decision_id)
    if decision is None or decision.session_id != session_id:
        raise HTTPException(status_code=404, detail="adoption_decision_not_found")
    commit = AdoptionCommitService(variable_hub_repository=repos["variable_hub"]).commit(
        session=session,
        decision=decision,
    )
    with sqlite_writes_bypass_queue():
        repos["adoption"].save_commit(commit)
        repos["session"].save(session)
    _publish_autopilot_session_state(session)
    return {
        "session": _session_payload(session),
        "commit": _commit_payload(commit),
        "next_action": _next_action(session.status),
    }


def _next_action(status) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    if value == InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW.value:
        return "pre_call_review_required"
    if value == InvocationSessionStatus.AWAITING_ACCEPTANCE.value:
        return "acceptance_required"
    if value == InvocationSessionStatus.AWAITING_COMMIT.value:
        return "commit_required"
    if value == InvocationSessionStatus.GENERATING.value:
        return "generating"
    if value == InvocationSessionStatus.COMPLETED.value:
        return "completed"
    if value == InvocationSessionStatus.BLOCKED.value:
        return "blocked"
    return "none"
