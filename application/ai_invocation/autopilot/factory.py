"""Factory helpers for autopilot AI Invocation wiring."""
from __future__ import annotations

from typing import Any

from application.ai_invocation.autopilot.orchestrator import AutopilotInvocationOrchestrator
from application.ai_invocation.autopilot.publisher import AutopilotSessionPublisher


def get_or_create_autopilot_orchestrator(host: Any) -> AutopilotInvocationOrchestrator:
    orchestrator = getattr(host, "_autopilot_invocation_orchestrator", None)
    if orchestrator is not None:
        return orchestrator

    llm_service = getattr(host, "llm_service", None)
    if llm_service is None:
        raise RuntimeError("autopilot invocation orchestrator requires llm_service")

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
    orchestrator = AutopilotInvocationOrchestrator(
        spec_service=InvocationSpecService(SqliteInvocationSpecRepository(db)),
        variable_resolver=VariableResolver(SqliteVariableHubRepository(db)),
        prompt_assembler=CPMSPromptAssembler(),
        llm_service=llm_service,
        publisher=AutopilotSessionPublisher(),
        session_service=InvocationSessionService(),
        attempt_service=AttemptService(llm_service),
        adoption_service=AdoptionService(),
        commit_service=AdoptionCommitService(variable_hub_repository=SqliteVariableHubRepository(db)),
        session_repository=SqliteInvocationSessionRepository(db),
        attempt_repository=SqliteInvocationAttemptRepository(db),
        adoption_repository=SqliteAdoptionRepository(db),
    )
    setattr(host, "_autopilot_invocation_orchestrator", orchestrator)
    return orchestrator
