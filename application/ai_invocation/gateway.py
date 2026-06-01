"""AIInvocationGateway：AI 调用唯一编排入口。"""
from __future__ import annotations

from typing import Callable

from domain.ai.services.llm_service import GenerationConfig, LLMService
from application.ai_invocation.dtos import (
    ContinuationRef,
    InvocationPolicy,
    InvocationRequest,
    InvocationResult,
    InvocationSessionStatus,
)
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.ai_invocation.services import AdoptionCommitService, AdoptionService, AttemptService, InvocationSessionService
from application.ai_invocation.spec_service import InvocationSpecService
from application.ai_invocation.variable_hub import VariableResolver


class AIInvocationGateway:
    """统一 AI 调用编排入口。

    Gateway 只负责编排公共前缀和状态流转，不拼 prompt、不读取业务表、
    不判断章节或页面逻辑。
    """

    def __init__(
        self,
        *,
        spec_service: InvocationSpecService,
        variable_resolver: VariableResolver,
        prompt_assembler: CPMSPromptAssembler,
        llm_service: LLMService,
        session_service: InvocationSessionService | None = None,
        attempt_service: AttemptService | None = None,
        adoption_service: AdoptionService | None = None,
        commit_service: AdoptionCommitService | None = None,
    ):
        self._spec_service = spec_service
        self._variable_resolver = variable_resolver
        self._prompt_assembler = prompt_assembler
        self._session_service = session_service or InvocationSessionService()
        self._attempt_service = attempt_service or AttemptService(llm_service)
        self._adoption_service = adoption_service or AdoptionService()
        self._commit_service = commit_service or AdoptionCommitService()

    async def invoke(self, request: InvocationRequest) -> InvocationResult:
        spec = self._spec_service.load(request)
        policy = request.policy or spec.default_policy
        session = self._session_service.create(
            operation=request.operation,
            node_key=request.node_key,
            policy=policy,
            context=request.context,
            continuation=request.continuation
            or (
                ContinuationRef(handler_key=spec.continuation_handler_key)
                if spec.continuation_handler_key
                else None
            ),
            metadata=request.metadata,
        )
        self._session_service.update_status(session, InvocationSessionStatus.SPEC_RESOLVED)
        self._session_service.update_status(session, InvocationSessionStatus.CONTEXT_RESOLVED)

        variable_plan = self._variable_resolver.resolve(
            spec=spec,
            explicit_variables=request.variables,
            context=request.context,
        )
        self._session_service.update_status(session, InvocationSessionStatus.VARIABLES_RESOLVED)
        prompt_snapshot = self._prompt_assembler.compile(spec=spec, variable_plan=variable_plan)
        self._session_service.attach_prompt(session, prompt_snapshot, variable_plan)

        if not variable_plan.ok:
            session.status = InvocationSessionStatus.BLOCKED
            return InvocationResult(
                session=session,
                prompt_snapshot=prompt_snapshot,
                variable_plan=variable_plan,
            )

        if policy in {InvocationPolicy.REVIEW_BEFORE_CALL, InvocationPolicy.FULL_INTERACTIVE, InvocationPolicy.AUTOPILOT_PAUSE}:
            session.status = InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW
            return InvocationResult(
                session=session,
                prompt_snapshot=prompt_snapshot,
                variable_plan=variable_plan,
            )

        attempt = await self._attempt_service.generate(
            session=session,
            prompt_snapshot=prompt_snapshot,
            config=request.config,
        )
        if policy == InvocationPolicy.REVIEW_AFTER_CALL:
            session.status = InvocationSessionStatus.AWAITING_ACCEPTANCE
            return InvocationResult(
                session=session,
                attempt=attempt,
                prompt_snapshot=prompt_snapshot,
                variable_plan=variable_plan,
            )
        else:
            decision = self._adoption_service.accept(
                session=session,
                attempt=attempt,
                accepted_by="system",
                metadata={"auto_accept_policy": policy.value},
            )
            commit = self._commit_service.commit(session=session, decision=decision)
            return InvocationResult(
                session=session,
                attempt=attempt,
                decision=decision,
                commit=commit,
                prompt_snapshot=prompt_snapshot,
                variable_plan=variable_plan,
            )

    def prepare(self, request: InvocationRequest) -> InvocationResult:
        """Run the common invocation prefix and return a persisted-ready session.

        This is used by long-running streaming callers that need to drive the
        attempt loop themselves while still freezing spec, variables, and prompt
        snapshots through the same control plane.
        """
        spec = self._spec_service.load(request)
        policy = request.policy or spec.default_policy
        session = self._session_service.create(
            operation=request.operation,
            node_key=request.node_key,
            policy=policy,
            context=request.context,
            continuation=request.continuation
            or (
                ContinuationRef(handler_key=spec.continuation_handler_key)
                if spec.continuation_handler_key
                else None
            ),
            metadata=request.metadata,
        )
        self._session_service.update_status(session, InvocationSessionStatus.SPEC_RESOLVED)
        self._session_service.update_status(session, InvocationSessionStatus.CONTEXT_RESOLVED)
        variable_plan = self._variable_resolver.resolve(
            spec=spec,
            explicit_variables=request.variables,
            context=request.context,
        )
        self._session_service.update_status(session, InvocationSessionStatus.VARIABLES_RESOLVED)
        prompt_snapshot = self._prompt_assembler.compile(spec=spec, variable_plan=variable_plan)
        self._session_service.attach_prompt(session, prompt_snapshot, variable_plan)
        if not variable_plan.ok:
            session.status = InvocationSessionStatus.BLOCKED
        return InvocationResult(
            session=session,
            prompt_snapshot=prompt_snapshot,
            variable_plan=variable_plan,
        )

    async def generate_prepared_streaming(
        self,
        *,
        session,
        prompt_snapshot,
        config: GenerationConfig | None = None,
        on_chunk: Callable[[str, str], None] | None = None,
    ) -> InvocationResult:
        attempt = await self._attempt_service.generate_streaming(
            session=session,
            prompt_snapshot=prompt_snapshot,
            config=config,
            on_chunk=on_chunk,
        )
        if session.policy == InvocationPolicy.REVIEW_AFTER_CALL:
            session.status = InvocationSessionStatus.AWAITING_ACCEPTANCE
            return InvocationResult(
                session=session,
                attempt=attempt,
                prompt_snapshot=prompt_snapshot,
                variable_plan=session.variable_plan,
            )
        decision = self._adoption_service.accept(
            session=session,
            attempt=attempt,
            accepted_by="system",
            metadata={"auto_accept_policy": session.policy.value},
        )
        commit = self._commit_service.commit(session=session, decision=decision)
        return InvocationResult(
            session=session,
            attempt=attempt,
            decision=decision,
            commit=commit,
            prompt_snapshot=prompt_snapshot,
            variable_plan=session.variable_plan,
        )
