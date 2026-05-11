"""DAG 运行时投影 — 将全托管共享状态映射为 DAG 节点状态

设计目标（顶级可扩展性）：
1. **单一数据类** ``NarrativeRuntimeSnapshot``：所有输入来自共享 dict，字段可增不改名。
2. **管线序列表** ``PIPELINE_ORDER``：与 ``application.engine.dag.models.get_default_dag`` 节点集合一致；
   新增默认节点时，只需 append / 插入此表 + 可选在 ``_resolve_primary_node`` 增加分支。
3. **纯函数** ``project_node_states``：无副作用，便于单测与将来接入真 DAG 引擎事件流。

不依赖 FastAPI，避免循环 import。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

# 与 get_default_dag() 中节点 id 顺序一致（用于「已完成 → success」波浪）
PIPELINE_ORDER: Tuple[str, ...] = (
    "ctx_blueprint",
    "ctx_memory",
    "ctx_foreshadow",
    "ctx_voice",
    "ctx_debt",
    "exec_beat",
    "exec_writer",
    "val_style",
    "val_tension",
    "val_anti_ai",
    "gw_circuit",
    "val_narrative",
    "val_foreshadow",
    "val_kg_infer",
    "gw_review",
    "gw_retry",
)

_ORDER_INDEX = {nid: i for i, nid in enumerate(PIPELINE_ORDER)}


@dataclass(frozen=True)
class NarrativeRuntimeSnapshot:
    """从共享内存抽取的叙事引擎一帧（可扩展字段在此集中声明）。"""

    novel_id: str
    autopilot_status: str
    current_stage: str
    writing_substep: str
    audit_progress: Optional[str]


def snapshot_from_shared(novel_id: str, shared: Mapping[str, Any]) -> NarrativeRuntimeSnapshot:
    ap = str(shared.get("autopilot_status") or "stopped").strip().lower()
    st = str(shared.get("current_stage") or "planning").strip().lower()
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


def _audit_substep_to_node(ws: str) -> Optional[str]:
    return {
        "audit_voice_check": "val_style",
        "audit_tension": "val_tension",
        "audit_aftermath": "val_narrative",
        "audit_anti_ai": "val_anti_ai",
    }.get(ws)


def _audit_progress_to_node(ap: Optional[str]) -> Optional[str]:
    if not ap:
        return None
    return {
        "voice_check": "val_style",
        "tension": "val_tension",
        "aftermath": "val_narrative",
        "anti_ai": "val_anti_ai",
    }.get(ap)


def _resolve_primary_node(s: NarrativeRuntimeSnapshot) -> Optional[Tuple[str, str]]:
    """返回 (node_id, status) ；status 与前端 NodeStatus 对齐。"""
    if s.autopilot_status == "error":
        return ("gw_circuit", "error")

    if s.autopilot_status != "running":
        return None

    ws = s.writing_substep
    st = s.current_stage

    # 细粒度子步骤优先（写作 / 审计）
    if ws:
        if ws == "macro_planning":
            return ("ctx_blueprint", "running")
        if ws == "act_planning":
            return ("ctx_memory", "running")
        if ws == "llm_calling":
            return ("exec_writer", "running")
        if ws in ("chapter_found", "context_assembly", "beat_magnification"):
            return ("exec_beat", "running")
        if ws in ("soft_landing", "persisting", "continuity_check", "chapter_persist"):
            return ("exec_writer", "running")
        aid = _audit_substep_to_node(ws)
        if aid:
            return (aid, "running")

    if st in ("macro_planning", "planning"):
        return ("ctx_blueprint", "running")
    if st == "act_planning":
        return ("ctx_memory", "running")

    if st == "writing":
        return ("exec_writer", "running")

    if st == "auditing":
        nid = _audit_progress_to_node(s.audit_progress) or "val_style"
        return (nid, "running")

    if st == "paused_for_review":
        return ("gw_review", "warning")

    if st == "completed":
        return ("gw_review", "completed")

    return ("ctx_blueprint", "pending")


def project_node_states(
    node_ids_enabled: List[Tuple[str, bool]],
    snapshot: NarrativeRuntimeSnapshot,
) -> Dict[str, Dict[str, Any]]:
    """node_id -> {status, enabled}，供 ``GET /dag/.../status`` 与 SSE 使用。"""
    out: Dict[str, Dict[str, Any]] = {}

    if snapshot.autopilot_status == "error":
        for nid, enabled in node_ids_enabled:
            if not enabled:
                out[nid] = {"status": "disabled", "enabled": False}
            elif nid == "gw_circuit":
                out[nid] = {"status": "error", "enabled": True}
            else:
                out[nid] = {"status": "idle", "enabled": True}
        return out

    primary = _resolve_primary_node(snapshot)
    primary_id = primary[0] if primary else None
    primary_status = primary[1] if primary else None
    p_idx = _ORDER_INDEX.get(primary_id, -1) if primary_id else -1

    # 全书完成：管线节点一律 success（网关收尾）
    all_success = (
        snapshot.autopilot_status == "stopped"
        and snapshot.current_stage == "completed"
    ) or snapshot.autopilot_status == "completed"

    for nid, enabled in node_ids_enabled:
        if not enabled:
            out[nid] = {"status": "disabled", "enabled": False}
            continue

        if all_success and nid in _ORDER_INDEX:
            out[nid] = {"status": "success", "enabled": True}
            continue

        if snapshot.autopilot_status != "running":
            out[nid] = {"status": "idle", "enabled": True}
            continue

        if primary_id and snapshot.autopilot_status == "running":
            j = _ORDER_INDEX.get(nid, -1)
            if j >= 0 and p_idx >= 0 and j < p_idx:
                out[nid] = {"status": "success", "enabled": True}
            elif nid == primary_id and primary_status:
                out[nid] = {"status": primary_status, "enabled": True}
            else:
                out[nid] = {"status": "idle", "enabled": True}
        else:
            out[nid] = {"status": "idle", "enabled": True}

    return out


def node_states_to_sse_events(
    novel_id: str,
    prev: Dict[str, Dict[str, Any]],
    new: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """生成 node_status_change 事件列表（仅变化节点）。"""
    events: List[Dict[str, Any]] = []
    keys = set(prev) | set(new)
    for nid in keys:
        a = prev.get(nid) or {}
        b = new.get(nid) or {}
        if a.get("status") == b.get("status") and a.get("enabled") == b.get("enabled"):
            continue
        st = b.get("status", "idle")
        events.append(
            {
                "type": "node_status_change",
                "novel_id": novel_id,
                "node_id": nid,
                "timestamp": time.time(),
                "status": st,
            }
        )
    return events
