"""AI Invocation 会话与 attempt 服务。"""
from __future__ import annotations

import uuid

from domain.ai.services.llm_service import GenerationConfig, LLMService
from application.ai_invocation.dtos import (
    AdoptionCommit,
    AdoptionCommitStatus,
    AdoptionCommitStep,
    AdoptionDecision,
    InvocationAttempt,
    InvocationAttemptStatus,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    PromptSnapshot,
    stable_hash,
)


class InvocationSessionService:
    """管理 invocation session 的最小服务。"""

    def __init__(self):
        self._sessions: dict[str, InvocationSession] = {}

    def create(
        self,
        *,
        operation: str,
        node_key: str,
        policy: InvocationPolicy,
        context,
        continuation=None,
        metadata=None,
    ) -> InvocationSession:
        session = InvocationSession(
            id=str(uuid.uuid4()),
            operation=operation,
            node_key=node_key,
            policy=policy,
            context=dict(context or {}),
            continuation=continuation,
            metadata=dict(metadata or {}),
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> InvocationSession:
        return self._sessions[session_id]

    def update_status(self, session: InvocationSession, status: InvocationSessionStatus) -> None:
        session.status = status

    def attach_prompt(self, session: InvocationSession, snapshot: PromptSnapshot, variable_plan) -> None:
        session.prompt_snapshot = snapshot
        session.variable_plan = variable_plan
        session.status = InvocationSessionStatus.PROMPT_COMPILED


class AttemptService:
    """创建 attempt 并统一调用 LLMService。"""

    def __init__(self, llm_service: LLMService):
        self._llm_service = llm_service
        self._attempts: dict[str, InvocationAttempt] = {}

    async def generate(
        self,
        *,
        session: InvocationSession,
        prompt_snapshot: PromptSnapshot,
        config: GenerationConfig | None = None,
    ) -> InvocationAttempt:
        attempt = InvocationAttempt(
            id=str(uuid.uuid4()),
            session_id=session.id,
            status=InvocationAttemptStatus.RUNNING,
            prompt_snapshot=prompt_snapshot,
        )
        self._attempts[attempt.id] = attempt
        session.attempts.append(attempt.id)
        session.status = InvocationSessionStatus.GENERATING
        try:
            result = await self._llm_service.generate(prompt_snapshot.prompt, config or GenerationConfig())
            attempt.content = result.content
            attempt.token_usage = result.token_usage
            attempt.status = InvocationAttemptStatus.SUCCEEDED
            return attempt
        except Exception as exc:
            attempt.status = InvocationAttemptStatus.FAILED
            attempt.error = str(exc)
            session.status = InvocationSessionStatus.FAILED
            raise

    def get(self, attempt_id: str) -> InvocationAttempt:
        return self._attempts[attempt_id]


class AdoptionService:
    """形成采纳或拒绝决策，不执行提交副作用。"""

    def __init__(self):
        self._decisions: dict[str, AdoptionDecision] = {}

    def accept(
        self,
        *,
        session: InvocationSession,
        attempt: InvocationAttempt,
        accepted_by: str = "system",
        commit_prompt_version: bool = False,
        commit_variable_outputs: bool = False,
        commit_variable_bindings: bool = False,
        metadata: dict | None = None,
    ) -> AdoptionDecision:
        if attempt.session_id != session.id:
            raise ValueError("attempt 不属于当前 invocation session")
        if attempt.status != InvocationAttemptStatus.SUCCEEDED:
            raise ValueError("只有成功的 attempt 可以被采纳")
        decision = AdoptionDecision(
            id=str(uuid.uuid4()),
            session_id=session.id,
            attempt_id=attempt.id,
            accept_content=True,
            commit_prompt_version=commit_prompt_version,
            commit_variable_outputs=commit_variable_outputs,
            commit_variable_bindings=commit_variable_bindings,
            accepted_content=attempt.content,
            accepted_by=accepted_by,
            metadata=dict(metadata or {}),
        )
        self._decisions[decision.id] = decision
        session.status = InvocationSessionStatus.AWAITING_COMMIT
        return decision

    def reject(self, *, session: InvocationSession, attempt: InvocationAttempt, accepted_by: str = "system") -> AdoptionDecision:
        if attempt.session_id != session.id:
            raise ValueError("attempt 不属于当前 invocation session")
        decision = AdoptionDecision(
            id=str(uuid.uuid4()),
            session_id=session.id,
            attempt_id=attempt.id,
            decision="rejected",
            accept_content=False,
            accepted_content="",
            accepted_by=accepted_by,
        )
        self._decisions[decision.id] = decision
        session.status = InvocationSessionStatus.CANCELLED
        return decision

    def get(self, decision_id: str) -> AdoptionDecision:
        return self._decisions[decision_id]


class AdoptionCommitService:
    """幂等提交采纳结果。

    当前只实现最小内容提交步骤；CPMS 版本、变量绑定、变量输出和 continuation
    后续通过独立 step 扩展，不能再绕回 Gateway 或业务层硬编码。
    """

    def __init__(self):
        self._commits_by_key: dict[str, AdoptionCommit] = {}

    def commit(self, *, session: InvocationSession, decision: AdoptionDecision) -> AdoptionCommit:
        if decision.session_id != session.id:
            raise ValueError("decision 不属于当前 invocation session")
        key = f"{session.id}:{decision.id}"
        existing = self._commits_by_key.get(key)
        if existing is not None:
            return existing
        if decision.decision != "accepted" or not decision.accept_content:
            session.status = InvocationSessionStatus.CANCELLED
            commit = AdoptionCommit(
                id=str(uuid.uuid4()),
                session_id=session.id,
                decision_id=decision.id,
                status=AdoptionCommitStatus.SUCCEEDED,
                steps=[
                    AdoptionCommitStep(
                        name="commit_content_patch",
                        status=AdoptionCommitStatus.SUCCEEDED,
                        result={"skipped": True, "reason": "decision_not_accepted"},
                    )
                ],
            )
            self._commits_by_key[key] = commit
            return commit

        session.status = InvocationSessionStatus.COMMITTING
        commit = AdoptionCommit(
            id=str(uuid.uuid4()),
            session_id=session.id,
            decision_id=decision.id,
            status=AdoptionCommitStatus.RUNNING,
        )
        try:
            commit.steps.append(
                AdoptionCommitStep(
                    name="commit_content_patch",
                    status=AdoptionCommitStatus.SUCCEEDED,
                    result={
                        "content_hash": stable_hash({"content": decision.accepted_content}),
                        "content_length": len(decision.accepted_content),
                    },
                )
            )
            commit.status = AdoptionCommitStatus.SUCCEEDED
            commit.result = {"accepted_content": decision.accepted_content}
            session.status = InvocationSessionStatus.COMPLETED
        except Exception as exc:
            commit.status = AdoptionCommitStatus.FAILED
            commit.error = str(exc)
            session.status = InvocationSessionStatus.FAILED
            raise
        finally:
            self._commits_by_key[key] = commit
        return commit
