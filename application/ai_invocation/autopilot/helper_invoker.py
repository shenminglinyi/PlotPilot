"""Helper invocations for autopilot-side secondary AI calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from application.ai_invocation.autopilot.intents import AutopilotInvocationIntent
from application.ai_invocation.dtos import InvocationPolicy


@dataclass(frozen=True)
class AutopilotHelperRequest:
    novel_id: str
    stage: str
    operation: str
    node_key: str
    explicit_variables: Mapping[str, Any] = field(default_factory=dict)
    context: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    config: Mapping[str, Any] = field(default_factory=dict)


class AutopilotHelperInvoker:
    """Internal helper AI calls that still publish AI Invocation panel state."""

    def __init__(self, *, orchestrator, db=None):
        self._orchestrator = orchestrator
        self._db = db

    async def invoke_text(self, request: AutopilotHelperRequest) -> str:
        from application.ai_invocation.contracts import ensure_invocation_contract
        from infrastructure.ai.prompt_utils import PromptTemplateUnavailable

        try:
            ensure_invocation_contract(request.operation, request.node_key, self._db)
        except Exception as exc:
            raise PromptTemplateUnavailable(
                f"AI invocation contract unavailable: {request.operation}/{request.node_key}: {exc}"
            ) from exc
        intent = AutopilotInvocationIntent(
            novel_id=request.novel_id,
            stage=request.stage,
            operation=request.operation,
            node_key=request.node_key,
            context=dict(request.context or {}),
            explicit_variables=dict(request.explicit_variables or {}),
            policy_hint=InvocationPolicy.DIRECT,
            metadata=dict(request.metadata or {}),
            config=dict(request.config or {}),
        )
        prepared = await self._orchestrator.prepare(intent)
        outcome = await self._orchestrator.complete_prepared(intent, prepared)
        if outcome.status != "completed":
            raise RuntimeError(
                f"Autopilot helper invocation did not complete: {request.operation}/{request.node_key} status={outcome.status}"
            )
        return outcome.accepted_content or ""
