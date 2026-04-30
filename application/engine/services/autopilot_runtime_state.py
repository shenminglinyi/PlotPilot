"""Process-local runtime state for the managed autopilot daemon.

The API process owns the daemon child process. Routes use this lightweight
state to avoid marking novels as running when the daemon is disabled or absent.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Optional


@dataclass(frozen=True)
class AutopilotRuntimeState:
    running: bool = False
    pid: Optional[int] = None
    disabled: bool = False
    reason: str = ""


_state = AutopilotRuntimeState(reason="守护进程尚未初始化")
_lock = Lock()


def set_autopilot_runtime_state(
    *,
    running: bool,
    pid: Optional[int] = None,
    disabled: bool = False,
    reason: str = "",
) -> None:
    global _state
    with _lock:
        _state = AutopilotRuntimeState(
            running=running,
            pid=pid,
            disabled=disabled,
            reason=reason,
        )


def get_autopilot_runtime_state() -> AutopilotRuntimeState:
    with _lock:
        return _state
