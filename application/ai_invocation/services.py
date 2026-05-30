"""AI Invocation 会话与 attempt 服务。"""
from __future__ import annotations

import uuid

from domain.ai.services.llm_service import GenerationConfig, LLMService
from application.ai_invocation.dtos import (
    InvocationAttempt,
    InvocationAttemptStatus,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    PromptSnapshot,
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
