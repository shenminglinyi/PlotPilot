"""Daemon-safe shared state helpers for autopilot invocation."""
from __future__ import annotations

import multiprocessing
import sys
import time
from typing import Any


def read_autopilot_shared_state(novel_id: str) -> dict[str, Any]:
    try:
        shared = sys.modules.get("__shared_state")
        if shared is not None:
            return dict(shared.get(f"novel:{novel_id}", {}) or {})
    except Exception:
        pass
    try:
        if multiprocessing.current_process().daemon:
            return {}
    except Exception:
        return {}
    try:
        from interfaces.main import get_shared_novel_state

        return dict(get_shared_novel_state(novel_id) or {})
    except Exception:
        return {}


def write_autopilot_shared_state(novel_id: str, **fields: Any) -> bool:
    try:
        shared = sys.modules.get("__shared_state")
        if shared is not None:
            key = f"novel:{novel_id}"
            current = dict(shared.get(key, {}) or {})
            current.update(fields)
            current["novel_id"] = novel_id
            current["_updated_at"] = time.time()
            shared["_daemon_heartbeat"] = time.time()
            shared[key] = current
            return True
    except Exception:
        pass
    try:
        if multiprocessing.current_process().daemon:
            return False
    except Exception:
        return False
    try:
        from interfaces.main import update_shared_novel_state

        update_shared_novel_state(novel_id, **fields)
        return True
    except Exception:
        return False
