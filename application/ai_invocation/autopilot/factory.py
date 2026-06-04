"""Factory helpers for autopilot AI Invocation wiring."""
from __future__ import annotations

from typing import Any

from application.ai_invocation.autopilot.helper_invoker import AutopilotHelperInvoker
from application.ai_invocation.autopilot.orchestrator import AutopilotInvocationOrchestrator
from application.ai_invocation.autopilot.publisher import AutopilotSessionPublisher


def _resolve_llm_service(owner: Any, explicit_llm_service: Any | None = None):
    llm_service = explicit_llm_service
    if llm_service is None:
        llm_service = getattr(owner, "llm_service", None)
    if llm_service is None:
        llm_service = getattr(owner, "_llm", None)
    if llm_service is None:
        raise RuntimeError("autopilot invocation orchestrator requires llm_service")
    return llm_service


def _build_orchestrator(*, llm_service, publisher) -> AutopilotInvocationOrchestrator:
    from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
    from application.ai_invocation.services import AdoptionCommitService, AdoptionService, AttemptService, InvocationSessionService
    from application.ai_invocation.spec_service import InvocationSpecService
    from application.ai_invocation.variable_hub import VariableResolver
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
        SqliteAdoptionRepository,
        SqliteInvocationAttemptRepository,
        SqliteInvocationSessionRepository,
        SqliteInvocationSpecRepository,
        SqliteVariableHubRepository,
    )

    db = get_database()
    return AutopilotInvocationOrchestrator(
        spec_service=InvocationSpecService(SqliteInvocationSpecRepository(db)),
        variable_resolver=VariableResolver(SqliteVariableHubRepository(db)),
        prompt_assembler=CPMSPromptAssembler(),
        llm_service=llm_service,
        publisher=publisher,
        session_service=InvocationSessionService(),
        attempt_service=AttemptService(llm_service),
        adoption_service=AdoptionService(),
        commit_service=AdoptionCommitService(variable_hub_repository=SqliteVariableHubRepository(db)),
        session_repository=SqliteInvocationSessionRepository(db),
        attempt_repository=SqliteInvocationAttemptRepository(db),
        adoption_repository=SqliteAdoptionRepository(db),
    )


def _build_publisher(owner: Any) -> AutopilotSessionPublisher:
    state_writer = getattr(owner, "_update_shared_state", None)
    if callable(state_writer):
        return AutopilotSessionPublisher(state_writer=state_writer)
    return AutopilotSessionPublisher()


def get_or_create_autopilot_orchestrator(host: Any) -> AutopilotInvocationOrchestrator:
    orchestrator = getattr(host, "_autopilot_invocation_orchestrator", None)
    if orchestrator is not None:
        return orchestrator

    orchestrator = _build_orchestrator(
        llm_service=_resolve_llm_service(host),
        publisher=_build_publisher(host),
    )
    setattr(host, "_autopilot_invocation_orchestrator", orchestrator)
    return orchestrator


def get_or_create_autopilot_helper_invoker(
    owner: Any,
    *,
    llm_service: Any | None = None,
) -> AutopilotHelperInvoker:
    helper = getattr(owner, "_autopilot_helper_invoker", None)
    if helper is not None:
        return helper

    from infrastructure.persistence.database.connection import get_database

    helper_orchestrator = _build_orchestrator(
        llm_service=_resolve_llm_service(owner, llm_service),
        publisher=_build_publisher(owner),
    )
    helper = AutopilotHelperInvoker(orchestrator=helper_orchestrator, db=get_database())
    setattr(owner, "_autopilot_helper_invoker", helper)
    return helper
