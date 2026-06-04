"""Publish autopilot invocation state into shared status."""
from __future__ import annotations

from typing import Any, Mapping

from application.ai_invocation.autopilot.shared_state import write_autopilot_shared_state


class AutopilotSessionPublisher:
    def __init__(self, state_writer=None):
        self._state_writer = state_writer

    def publish(self, novel_id: str, payload: Mapping[str, Any]) -> None:
        data = dict(payload)
        if self._state_writer is None:
            if write_autopilot_shared_state(novel_id, **data):
                return
        if self._state_writer is not None:
            self._state_writer(novel_id, **data)
