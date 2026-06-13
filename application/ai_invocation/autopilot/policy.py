"""Autopilot invocation policy resolution."""
from __future__ import annotations

from typing import Any, Mapping

from application.ai_invocation.dtos import InvocationPolicy


class AutopilotInvocationPolicyResolver:
    """Resolve autopilot policy from runtime hints and novel flags."""

    def resolve(
        self,
        *,
        operation: str,
        node_key: str,
        novel: Any = None,
        policy_hint: InvocationPolicy | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> InvocationPolicy:
        if policy_hint is not None:
            return policy_hint

        context = dict(context or {})
        auto_approve_mode = bool(getattr(novel, "auto_approve_mode", False))
        if str(context.get("force_interactive") or "").lower() in {"1", "true", "yes"}:
            return InvocationPolicy.AUTOPILOT_PAUSE
        if operation in {"autopilot.chapter.aftermath"}:
            return InvocationPolicy.DIRECT
        if auto_approve_mode:
            return InvocationPolicy.DIRECT
        if operation in {"autopilot.chapter.audit"}:
            return InvocationPolicy.DIRECT
        return InvocationPolicy.AUTOPILOT_PAUSE
