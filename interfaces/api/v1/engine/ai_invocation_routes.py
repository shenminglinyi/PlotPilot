"""AI Invocation API.

该路由只暴露统一 AI 调用会话，不在接口层拼接 prompt 或直接访问业务表。
"""
from __future__ import annotations

from typing import Any, Mapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from application.ai_invocation.dtos import (
    AdoptionCommit,
    AdoptionCommitStatus,
    AdoptionCommitStep,
    InvocationPolicy,
    InvocationRequest,
    InvocationSessionStatus,
)
from application.ai_invocation.gateway import AIInvocationGateway
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.ai_invocation.services import AdoptionCommitService, AdoptionService, AttemptService, InvocationSessionService
from application.ai_invocation.spec_service import InvocationSpecNotFoundError, InvocationSpecService
from application.ai_invocation.variable_hub import VariableResolver
from domain.ai.services.llm_service import GenerationConfig
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


def _config_from_dict(raw: Mapping[str, Any] | None) -> GenerationConfig | None:
    if not raw:
        return None
    return GenerationConfig(
        model=str(raw.get("model") or ""),
        max_tokens=int(raw.get("max_tokens") or 4096),
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
        "error": commit.error,
    }


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
    return {"session": _session_payload(session), "next_action": _next_action(session.status)}


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
    commit = AdoptionCommit(
        id=repos["adoption"].create_commit(session_id=session_id, decision_id=decision.id).id,
        session_id=session_id,
        decision_id=decision.id,
        status=AdoptionCommitStatus.SUCCEEDED,
        steps=[
            AdoptionCommitStep(
                name="commit_content_patch",
                status=AdoptionCommitStatus.SUCCEEDED,
                result={"content_length": len(decision.accepted_content)},
            )
        ],
        result={"accepted_content": decision.accepted_content},
    )
    with sqlite_writes_bypass_queue():
        repos["adoption"].save_commit(commit)
        session.status = InvocationSessionStatus.COMPLETED
        repos["session"].save(session)
    return {
        "session": _session_payload(session),
        "commit": _commit_payload(commit),
        "next_action": "completed",
    }


def _next_action(status) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    if value == InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW.value:
        return "pre_call_review_required"
    if value == InvocationSessionStatus.AWAITING_ACCEPTANCE.value:
        return "acceptance_required"
    if value == InvocationSessionStatus.AWAITING_COMMIT.value:
        return "commit_required"
    if value == InvocationSessionStatus.COMPLETED.value:
        return "completed"
    if value == InvocationSessionStatus.BLOCKED.value:
        return "blocked"
    return "none"
