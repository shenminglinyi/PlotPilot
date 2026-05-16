"""DAG 运行时投影 — 将全托管共享状态映射为 DAG 节点状态

设计：
1. **快照**见 ``runtime_snapshot``；**主节点语义**见 ``primary_node_policy``（声明式规则表）。
2. **管线顺序**来自 ``linkage_kernel.default_pipeline_node_ids()``（与 ``get_default_dag().nodes`` 一致）。
3. ``project_node_states`` 接收 ``(node_id, node_type, enabled)``，主节点高亮由 **type → id** 解析，适配自定义 DAG。

不依赖 FastAPI。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from domain.novel.entities.novel import AutopilotStatus, NovelStage

from application.engine.narrative_projection.linkage_kernel import default_pipeline_node_ids
from application.engine.narrative_projection.primary_node_policy import (
    DEFAULT_SEMANTICS,
    ProjectionSemantics,
    first_node_id_for_type,
    resolve_primary_node_type,
)
from application.engine.narrative_projection.runtime_snapshot import (
    NarrativeRuntimeSnapshot,
    fingerprint,
    snapshot_from_shared,
)

# 与 ``get_default_dag().nodes`` 声明顺序一致（单一数据源：linkage_kernel）
_PIPELINE_IDS = default_pipeline_node_ids()
_ORDER_INDEX = {nid: i for i, nid in enumerate(_PIPELINE_IDS)}


def project_node_states(
    nodes: Sequence[Tuple[str, str, bool]],
    snapshot: NarrativeRuntimeSnapshot,
    *,
    semantics: ProjectionSemantics = DEFAULT_SEMANTICS,
) -> Dict[str, Dict[str, Any]]:
    """``nodes`` 为 ``(node_id, node_type, enabled)``；返回 ``node_id -> {status, enabled}``。"""
    out: Dict[str, Dict[str, Any]] = {}

    if snapshot.autopilot_status == AutopilotStatus.ERROR.value:
        pt = resolve_primary_node_type(snapshot, semantics)
        err_type = pt[0] if pt else semantics.error_highlight_node_type
        err_id = first_node_id_for_type(nodes, err_type) or err_type
        for nid, _ntype, enabled in nodes:
            if not enabled:
                out[nid] = {"status": "disabled", "enabled": False}
            elif nid == err_id:
                out[nid] = {"status": "error", "enabled": True}
            else:
                out[nid] = {"status": "idle", "enabled": True}
        return out

    primary_sem = resolve_primary_node_type(snapshot, semantics)
    primary_type = primary_sem[0] if primary_sem else None
    primary_status = primary_sem[1] if primary_sem else None
    primary_id = (
        first_node_id_for_type(nodes, primary_type) if primary_type else None
    ) or primary_type

    p_idx = _ORDER_INDEX.get(primary_id, -1) if primary_id else -1

    all_success = (
        snapshot.autopilot_status == AutopilotStatus.STOPPED.value
        and snapshot.current_stage == NovelStage.COMPLETED.value
    ) or snapshot.autopilot_status == "completed"

    for nid, _ntype, enabled in nodes:
        if not enabled:
            out[nid] = {"status": "disabled", "enabled": False}
            continue

        if all_success and nid in _ORDER_INDEX:
            out[nid] = {"status": "success", "enabled": True}
            continue

        if snapshot.autopilot_status != AutopilotStatus.RUNNING.value:
            out[nid] = {"status": "idle", "enabled": True}
            continue

        if primary_id and snapshot.autopilot_status == AutopilotStatus.RUNNING.value:
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


__all__ = [
    "NarrativeRuntimeSnapshot",
    "fingerprint",
    "node_states_to_sse_events",
    "project_node_states",
    "snapshot_from_shared",
]
