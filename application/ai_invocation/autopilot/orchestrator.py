"""Autopilot invocation orchestration."""
from __future__ import annotations

from dataclasses import replace

from application.ai_invocation.autopilot.continuations import register_autopilot_continuations
from application.ai_invocation.autopilot.intents import AutopilotInvocationIntent, AutopilotInvocationOutcome
from application.ai_invocation.dtos import (
    ContinuationRef,
    InvocationAttemptStatus,
    InvocationPolicy,
    InvocationRequest,
    InvocationSessionStatus,
)
from application.ai_invocation.gateway import AIInvocationGateway
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.ai_invocation.services import AdoptionCommitService, AdoptionService, AttemptService, InvocationSessionService
from application.ai_invocation.spec_service import InvocationSpecService
from application.ai_invocation.variable_hub import VariableResolver
from typing import Any, Callable


class AutopilotInvocationOrchestrator:
    def __init__(
        self,
        *,
        spec_service: InvocationSpecService,
        variable_resolver: VariableResolver,
        prompt_assembler: CPMSPromptAssembler,
        llm_service: Any,
        publisher=None,
        session_service: InvocationSessionService | None = None,
        attempt_service: AttemptService | None = None,
        adoption_service: AdoptionService | None = None,
        commit_service: AdoptionCommitService | None = None,
        session_repository=None,
        attempt_repository=None,
        adoption_repository=None,
    ):
        register_autopilot_continuations()
        self._gateway = AIInvocationGateway(
            spec_service=spec_service,
            variable_resolver=variable_resolver,
            prompt_assembler=prompt_assembler,
            llm_service=llm_service,
            session_service=session_service,
            attempt_service=attempt_service,
            adoption_service=adoption_service,
            commit_service=commit_service,
        )
        self._publisher = publisher
        self._session_repository = session_repository
        self._attempt_repository = attempt_repository
        self._adoption_repository = adoption_repository

    def _publish(self, intent: AutopilotInvocationIntent, result) -> None:
        if self._publisher is None:
            return
        session = result.session
        status_value = session.status.value if hasattr(session.status, "value") else str(session.status)
        policy_value = session.policy.value if hasattr(session.policy, "value") else str(session.policy)
        self._publisher.publish(
            intent.novel_id,
            {
                "active_invocation_session_id": session.id,
                "active_invocation_operation": session.operation,
                "active_invocation_node_key": session.node_key,
                "active_invocation_status": status_value,
                "active_invocation_policy": policy_value,
                "requires_ai_review": session.status in {
                    InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
                    InvocationSessionStatus.AWAITING_ACCEPTANCE,
                    InvocationSessionStatus.AWAITING_COMMIT,
                    InvocationSessionStatus.BLOCKED,
                },
                "autopilot_pause_reason": "awaiting_ai_review"
                if session.status in {
                    InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
                    InvocationSessionStatus.AWAITING_ACCEPTANCE,
                    InvocationSessionStatus.AWAITING_COMMIT,
                    InvocationSessionStatus.BLOCKED,
                }
                else "",
            },
        )

    async def prepare(self, intent: AutopilotInvocationIntent):
        request = InvocationRequest(
            operation=intent.operation,
            node_key=intent.node_key,
            variables=dict(intent.explicit_variables or {}),
            context=dict(intent.context or {}),
            policy=intent.policy_hint or InvocationPolicy.AUTOPILOT_PAUSE,
            continuation=ContinuationRef(
                handler_key=intent.continuation_handler_key or "autopilot_outline_partition"
            ),
            metadata={**dict(intent.metadata or {}), "novel_id": intent.novel_id, "stage": intent.stage},
            config=None,
        )
        result = self._gateway.prepare(request)
        self._save_result(result)
        self._publish(intent, result)
        return result

    async def request(self, intent: AutopilotInvocationIntent) -> AutopilotInvocationOutcome:
        result = await self._gateway.invoke(
            InvocationRequest(
                operation=intent.operation,
                node_key=intent.node_key,
                variables=dict(intent.explicit_variables or {}),
                context=dict(intent.context or {}),
                policy=intent.policy_hint or InvocationPolicy.AUTOPILOT_PAUSE,
                continuation=ContinuationRef(
                    handler_key=intent.continuation_handler_key or "autopilot_outline_partition"
                ),
                metadata={**dict(intent.metadata or {}), "novel_id": intent.novel_id, "stage": intent.stage},
                config=None,
            )
        )
        session = result.session
        self._save_result(result)
        self._publish(intent, result)
        return AutopilotInvocationOutcome(
            session_id=session.id,
            status=session.status.value if hasattr(session.status, "value") else str(session.status),
            next_action=result.commit.status.value if result.commit else "",
            accepted_content=result.decision.accepted_content if result.decision else "",
            attempt_id=result.attempt.id if result.attempt else "",
            node_key=session.node_key,
            operation=session.operation,
            autopilot_pause_reason="awaiting_ai_review"
            if session.status in {
                InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
                InvocationSessionStatus.AWAITING_ACCEPTANCE,
                InvocationSessionStatus.AWAITING_COMMIT,
                InvocationSessionStatus.BLOCKED,
            }
            else "",
            payload={
                "session": session,
                "attempt": result.attempt,
                "decision": result.decision,
                "commit": result.commit,
                "prompt_snapshot": result.prompt_snapshot,
                "variable_plan": result.variable_plan,
            },
        )

    async def generate_prepared_streaming(
        self,
        *,
        intent: AutopilotInvocationIntent,
        prepared_result,
        config=None,
        on_chunk: Callable[[str, str], bool | None] | None = None,
    ) -> AutopilotInvocationOutcome:
        session = prepared_result.session
        if session.status in {
            InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
            InvocationSessionStatus.BLOCKED,
        }:
            return AutopilotInvocationOutcome(
                session_id=session.id,
                status=session.status.value if hasattr(session.status, "value") else str(session.status),
                node_key=session.node_key,
                operation=session.operation,
                autopilot_pause_reason="awaiting_ai_review",
                payload={
                    "session": session,
                    "attempt": None,
                    "decision": None,
                    "commit": None,
                    "prompt_snapshot": prepared_result.prompt_snapshot,
                    "variable_plan": prepared_result.variable_plan,
                },
            )
        attempt = await self._gateway._attempt_service.generate_streaming(
            session=session,
            prompt_snapshot=prepared_result.prompt_snapshot,
            config=config,
            on_chunk=on_chunk,
        )
        if session.policy == InvocationPolicy.REVIEW_AFTER_CALL:
            session.status = InvocationSessionStatus.AWAITING_ACCEPTANCE
            prepared_result = replace(
                prepared_result,
                attempt=attempt,
            )
            self._save_result(prepared_result)
            self._publish(intent, prepared_result)
            return AutopilotInvocationOutcome(
                session_id=session.id,
                status=session.status.value if hasattr(session.status, "value") else str(session.status),
                next_action="acceptance_required",
                accepted_content="",
                attempt_id=attempt.id,
                node_key=session.node_key,
                operation=session.operation,
                payload={
                    "session": session,
                    "attempt": attempt,
                    "decision": None,
                    "commit": None,
                    "prompt_snapshot": prepared_result.prompt_snapshot,
                    "variable_plan": prepared_result.variable_plan,
                },
            )
        if attempt.status != InvocationAttemptStatus.SUCCEEDED:
            if session.status != InvocationSessionStatus.CANCELLED:
                session.status = InvocationSessionStatus.FAILED
            prepared_result = replace(
                prepared_result,
                attempt=attempt,
            )
            self._save_result(prepared_result)
            self._publish(intent, prepared_result)
            return AutopilotInvocationOutcome(
                session_id=session.id,
                status=session.status.value if hasattr(session.status, "value") else str(session.status),
                next_action="cancelled" if session.status == InvocationSessionStatus.CANCELLED else "failed",
                accepted_content="",
                attempt_id=attempt.id,
                node_key=session.node_key,
                operation=session.operation,
                payload={
                    "session": session,
                    "attempt": attempt,
                    "decision": None,
                    "commit": None,
                    "prompt_snapshot": prepared_result.prompt_snapshot,
                    "variable_plan": prepared_result.variable_plan,
                },
            )
        decision = self._gateway._adoption_service.accept(
            session=session,
            attempt=attempt,
            accepted_by="system",
            metadata={"auto_accept_policy": session.policy.value},
        )
        result = self._gateway._commit_service.commit(session=session, decision=decision)
        prepared_result = replace(
            prepared_result,
            attempt=attempt,
            decision=decision,
            commit=result,
        )
        self._save_result(prepared_result)
        self._publish(intent, prepared_result)
        return AutopilotInvocationOutcome(
            session_id=session.id,
            status=session.status.value if hasattr(session.status, "value") else str(session.status),
            next_action=result.status.value if hasattr(result.status, "value") else str(result.status),
            accepted_content=decision.accepted_content,
            attempt_id=attempt.id,
            node_key=session.node_key,
            operation=session.operation,
            payload={
                "session": session,
                "attempt": attempt,
                "decision": decision,
                "commit": result,
                "prompt_snapshot": prepared_result.prompt_snapshot,
                "variable_plan": prepared_result.variable_plan,
            },
        )

    def _save_result(self, result) -> None:
        if self._session_repository is None:
            return
        from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

        with sqlite_writes_bypass_queue():
            self._session_repository.save(result.session)
            if result.attempt is not None and self._attempt_repository is not None:
                self._attempt_repository.save(result.attempt)
            if result.decision is not None and self._adoption_repository is not None:
                self._adoption_repository.save_decision(result.decision)
            if result.commit is not None and self._adoption_repository is not None:
                self._adoption_repository.save_commit(result.commit)
