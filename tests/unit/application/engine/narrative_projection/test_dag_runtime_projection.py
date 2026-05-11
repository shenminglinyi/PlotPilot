"""dag_runtime_projection — 共享状态 → DAG 节点状态"""
from __future__ import annotations

from application.engine.dag.models import get_default_dag
from application.engine.narrative_projection.dag_runtime_projection import (
    NarrativeRuntimeSnapshot,
    node_states_to_sse_events,
    project_node_states,
    snapshot_from_shared,
)


def _nodes_from_default_dag():
    dag = get_default_dag()
    return [(n.id, n.type, n.enabled) for n in dag.nodes]


def test_snapshot_from_shared_defaults():
    s = snapshot_from_shared("n1", {})
    assert s.autopilot_status == "stopped"
    assert s.current_stage == "planning"
    assert s.writing_substep == ""


def test_idle_when_stopped():
    s = NarrativeRuntimeSnapshot("n1", "stopped", "planning", "", None)
    out = project_node_states(_nodes_from_default_dag(), s)
    for nid, row in out.items():
        if row["enabled"]:
            assert row["status"] == "idle", nid


def test_error_marks_gw_circuit():
    s = NarrativeRuntimeSnapshot("n1", "error", "writing", "", None)
    out = project_node_states(_nodes_from_default_dag(), s)
    assert out["gw_circuit"]["status"] == "error"
    assert out["exec_writer"]["status"] == "idle"


def test_running_llm_calling_primary_writer_prior_success():
    s = NarrativeRuntimeSnapshot("n1", "running", "writing", "llm_calling", None)
    out = project_node_states(_nodes_from_default_dag(), s)
    assert out["exec_writer"]["status"] == "running"
    assert out["exec_beat"]["status"] == "success"
    assert out["ctx_blueprint"]["status"] == "success"


def test_book_completed_all_pipeline_success():
    s = NarrativeRuntimeSnapshot("n1", "stopped", "completed", "", None)
    out = project_node_states(_nodes_from_default_dag(), s)
    for nid in (
        "ctx_blueprint",
        "exec_writer",
        "gw_review",
    ):
        assert out[nid]["status"] == "success", nid


def test_auditing_audit_progress_aftermath_pipeline():
    s = NarrativeRuntimeSnapshot("n1", "running", "auditing", "", "aftermath_pipeline")
    out = project_node_states(_nodes_from_default_dag(), s)
    assert out["val_narrative"]["status"] == "running"


def test_auditing_audit_progress_tension_scoring():
    s = NarrativeRuntimeSnapshot("n1", "running", "auditing", "", "tension_scoring")
    out = project_node_states(_nodes_from_default_dag(), s)
    assert out["val_tension"]["status"] == "running"


def test_sse_events_only_on_diff():
    prev = {"a": {"status": "idle", "enabled": True}}
    new = {"a": {"status": "running", "enabled": True}}
    evs = node_states_to_sse_events("novel", prev, new)
    assert len(evs) == 1
    assert evs[0]["node_id"] == "a"
    assert evs[0]["status"] == "running"
