"""叙事运行时快照 — 与投影策略解耦，避免循环 import。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

from domain.novel.entities.novel import AutopilotStatus, NovelStage


@dataclass(frozen=True)
class NarrativeRuntimeSnapshot:
    """从共享内存抽取的叙事引擎一帧（可扩展字段在此集中声明）。"""

    novel_id: str
    autopilot_status: str
    current_stage: str
    writing_substep: str
    audit_progress: Optional[str]


def snapshot_from_shared(novel_id: str, shared: Mapping[str, Any]) -> NarrativeRuntimeSnapshot:
    ap = str(shared.get("autopilot_status") or AutopilotStatus.STOPPED.value).strip().lower()
    st = str(shared.get("current_stage") or NovelStage.PLANNING.value).strip().lower()
    ws = str(shared.get("writing_substep") or "").strip().lower()
    audit = shared.get("audit_progress")
    audit_s = str(audit).strip().lower() if audit is not None else None
    return NarrativeRuntimeSnapshot(
        novel_id=novel_id,
        autopilot_status=ap,
        current_stage=st,
        writing_substep=ws,
        audit_progress=audit_s or None,
    )


def fingerprint(s: NarrativeRuntimeSnapshot) -> Tuple[Any, ...]:
    """用于 SSE / 轮询去重。"""
    return (s.autopilot_status, s.current_stage, s.writing_substep, s.audit_progress)
