"""Process-shared runtime state accessors.

This module is the canonical import target for shared novel state. The legacy
``interfaces.main`` accessors re-export these functions for compatibility.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from interfaces.runtime import AppRuntime


logger = logging.getLogger(__name__)
_runtime = AppRuntime(logger)
_mp_manager: Any | None = None
_shared_state: dict | None = None


def _get_shared_state() -> dict:
    """Get the process-shared state dictionary, initializing it lazily."""
    global _mp_manager, _shared_state
    state = _runtime.get_shared_state()
    _mp_manager = _runtime._mp_manager
    _shared_state = state
    return state


def update_shared_novel_state(novel_id: str, **fields: Any) -> None:
    _runtime.update_shared_novel_state(novel_id, **fields)


def get_shared_novel_state(novel_id: str) -> Dict[str, Any]:
    return _runtime.get_shared_novel_state(novel_id)
