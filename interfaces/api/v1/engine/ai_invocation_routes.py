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
    prompt_hash,
    stable_hash,
)
from application.ai_invocation.gateway import AIInvocationGateway
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.ai_invocation.services import AdoptionCommitService, AdoptionService, AttemptService, InvocationSessionService
from application.ai_invocation.spec_service import InvocationSpecNotFoundError, InvocationSpecService
from application.ai_invocation.variable_hub import VariableResolver
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
    from application.blueprint.services.setup_main_plot_continuation import register_setup_main_plot_continuation
    from application.world.services.bible_setup_continuation import register_bible_setup_continuations

    register_autopilot_continuations()
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
    except Exception as exc:
        attempt.content = "".join(parts)
        attempt.status = InvocationAttemptStatus.FAILED
        attempt.error = str(exc)
        session.status = InvocationSessionStatus.FAILED
        with sqlite_writes_bypass_queue():
            repos["attempt"].save(attempt)
            repos["session"].save(session)
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

    render_result = get_template_engine().render(
        system_template=system_template,
        user_template=effective_user_template,
        variables=dict(session.variable_plan.aliases or {}),
    )
    prompt = Prompt(
        system=render_result.system or "",
        user=render_result.user or "",
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
    llm_service = get_llm_service()
    gateway = AIInvocationGateway(
        spec_service=InvocationSpecService(repos["spec"]),
        variable_resolver=VariableResolver(repos["variable_hub"]),
        prompt_assembler=CPMSPromptAssembler(),
        llm_service=llm_service,
        session_service=InvocationSessionService(),
        attempt_service=AttemptService(llm_service),
        adoption_service=AdoptionService(),
        commit_service=AdoptionCommitService(),
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _save_invocation_result(repos, result)

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
    if session.status != InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW:
        raise HTTPException(status_code=400, detail="invocation_session_not_waiting_for_pre_call_review")
    session.prompt_snapshot = _render_prompt_draft(session, request.system_template, request.user_template)
    with sqlite_writes_bypass_queue():
        repos["session"].save(session)
    return {
        "session": _session_payload(session),
        "next_action": _next_action(session.status),
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
    commit = AdoptionCommitService().commit(session=session, decision=decision)
    with sqlite_writes_bypass_queue():
        repos["adoption"].save_commit(commit)
        repos["session"].save(session)
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
