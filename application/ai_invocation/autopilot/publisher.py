"""Publish autopilot invocation state into shared status."""
from __future__ import annotations

from typing import Any, Mapping


class AutopilotSessionPublisher:
    def __init__(self, state_writer=None):
        self._state_writer = state_writer

    def publish(self, novel_id: str, payload: Mapping[str, Any]) -> None:
        if self._state_writer is None:
            try:
                from interfaces.main import update_shared_novel_state

                self._state_writer = update_shared_novel_state
            except Exception:
                self._state_writer = None
        if self._state_writer is None:
            return
        self._state_writer(novel_id, **dict(payload))
