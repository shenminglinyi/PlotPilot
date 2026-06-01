"""Autopilot invocation intents and outcomes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from application.ai_invocation.dtos import InvocationPolicy


@dataclass(frozen=True)
class AutopilotInvocationIntent:
    novel_id: str
    stage: str
    operation: str
    node_key: str
    context: Mapping[str, Any] = field(default_factory=dict)
    explicit_variables: Mapping[str, Any] = field(default_factory=dict)
    continuation_handler_key: str = ""
    policy_hint: Optional[InvocationPolicy] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutopilotInvocationOutcome:
    session_id: str
    status: str
    next_action: str = ""
    accepted_content: str = ""
    attempt_id: str = ""
    node_key: str = ""
    operation: str = ""
    autopilot_pause_reason: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
