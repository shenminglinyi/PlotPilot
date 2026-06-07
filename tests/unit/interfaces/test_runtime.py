from contextlib import nullcontext

from interfaces import runtime_state
from interfaces.runtime import AppRuntime, BackendLifecycle


def test_app_runtime_shared_novel_state_roundtrip():
    runtime = AppRuntime()
    runtime._shared_state = {}

    runtime.update_shared_novel_state("novel-1", stage="writing", progress=3)

    state = runtime.get_shared_novel_state("novel-1")
    assert state["novel_id"] == "novel-1"
    assert state["stage"] == "writing"
    assert state["progress"] == 3
    assert "_updated_at" in state


def test_app_runtime_missing_state_returns_empty_dict():
    runtime = AppRuntime()
    runtime._shared_state = {}

    assert runtime.get_shared_novel_state("missing") == {}


def test_runtime_state_module_is_canonical_shared_state_accessor(monkeypatch):
    runtime = AppRuntime()
    runtime._shared_state = {}
    monkeypatch.setattr(runtime_state, "_runtime", runtime)

    runtime_state.update_shared_novel_state("novel-2", stage="auditing")

    assert runtime_state.get_shared_novel_state("novel-2")["stage"] == "auditing"


def test_main_reexports_runtime_state_accessors():
    import interfaces.main as main

    assert main.get_shared_novel_state is runtime_state.get_shared_novel_state
    assert main.update_shared_novel_state is runtime_state.update_shared_novel_state
    assert main._get_shared_state is runtime_state._get_shared_state


def test_backend_lifecycle_startup_orchestrates_runtime_steps(monkeypatch):
    calls = []
    lifecycle = BackendLifecycle(
        start_daemon=lambda: calls.append("start_daemon"),
        stop_daemon=lambda: calls.append("stop_daemon"),
        cleanup_orphans=lambda: calls.append("cleanup_orphans"),
    )
    monkeypatch.setattr("interfaces.runtime.os.name", "nt")
    monkeypatch.setattr(
        "infrastructure.persistence.database.write_dispatch.startup_sqlite_writes_bypass_queue",
        lambda: nullcontext(),
    )
    monkeypatch.setattr(lifecycle, "stop_all_running_novels", lambda: calls.append("stop_running"))
    monkeypatch.setattr(lifecycle, "bootstrap_persistence_consumer", lambda: calls.append("persistence"))
    monkeypatch.setattr(lifecycle, "recover_drafts", lambda: calls.append("recover_drafts"))
    monkeypatch.setattr(lifecycle, "init_dag_node_registry", lambda: calls.append("dag_registry"))

    lifecycle.startup(registered_route_count=3)

    assert calls == [
        "cleanup_orphans",
        "stop_running",
        "persistence",
        "recover_drafts",
        "start_daemon",
        "dag_registry",
    ]


def test_backend_lifecycle_shutdown_orchestrates_cleanup(monkeypatch):
    calls = []
    lifecycle = BackendLifecycle(
        start_daemon=lambda: calls.append("start_daemon"),
        stop_daemon=lambda: calls.append("stop_daemon"),
        start_force_exit_watchdog=lambda: calls.append("watchdog"),
    )
    monkeypatch.setattr(lifecycle, "close_database", lambda skip_checkpoint: calls.append(f"db:{skip_checkpoint}"))
    monkeypatch.setattr(lifecycle, "checkpoint_sqlite_wal_safe", lambda: calls.append("wal"))
    monkeypatch.setattr(lifecycle, "close_llm_service", lambda: calls.append("llm"))
    monkeypatch.setattr(lifecycle, "log_stopped", lambda title: calls.append(title))

    lifecycle.shutdown()

    assert calls == [
        "watchdog",
        "stop_daemon",
        "db:True",
        "wal",
        "llm",
        "PlotPilot service stopped",
    ]
