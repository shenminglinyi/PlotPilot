"""新书向导 / Bible 异步生成：向 UI 暴露最近一次失败原因（内存态，单进程有效）。"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_lock = threading.Lock()
_by_novel: Dict[str, Dict[str, Any]] = {}


def clear_bible_generation_state(novel_id: str) -> None:
    with _lock:
        _by_novel.pop(novel_id, None)


def record_bible_generation_failure(novel_id: str, stage: str, message: str) -> None:
    text = (message or "").strip()
    if len(text) > 4000:
        text = text[:4000] + "…"
    with _lock:
        _by_novel[novel_id] = {
            "error": text,
            "stage": (stage or "").strip() or "unknown",
            "at": datetime.now(timezone.utc).isoformat(),
        }


def get_bible_generation_state(novel_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        row = _by_novel.get(novel_id)
        return dict(row) if row else None
