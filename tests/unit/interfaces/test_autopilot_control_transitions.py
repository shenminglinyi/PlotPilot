"""Exercise the API controls through their real single SQLite writer."""
import pytest
from fastapi import HTTPException

from application.engine.services import novel_stop_signal, persistence_queue, query_service
from application.engine.services.autopilot_recovery_policy import AutopilotRecoveryDecision, AutopilotRecoveryPolicy
from application.engine.services.shared_state_repository import SharedStateRepository
from domain.novel.entities.novel import AutopilotStatus, Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.narrative_progress import NARRATIVE_REVIEW_ISSUE
from infrastructure.persistence.database import connection
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from interfaces import runtime_state
from interfaces.runtime import AppRuntime
from interfaces.api.v1.engine import autopilot_routes as routes


@pytest.fixture
def book(tmp_path, monkeypatch):
    db = connection.DatabaseConnection(str(tmp_path / "plotpilot.db"))
    repo = SqliteNovelRepository(db)
    novel = Novel(NovelId("book"), "Book", "Author", 5, current_stage=NovelStage.WRITING,
                  autopilot_status=AutopilotStatus.RUNNING)
    with sqlite_writes_bypass_queue():
        repo.save(novel)
    monkeypatch.setattr(connection, "get_database", lambda *args: db)
    monkeypatch.setattr(routes, "get_novel_repository", lambda: repo)
    queue = persistence_queue.PersistenceQueue()
    pipe = queue.initialize()
    monkeypatch.setattr(persistence_queue, "_persistence_queue", queue)
    persistence_queue.register_persistence_handlers()
    queue.start_consumer()
    state = {}
    shared = SharedStateRepository(state)
    runtime = AppRuntime()
    monkeypatch.setattr(runtime, "get_shared_state", lambda: state)
    monkeypatch.setattr(runtime_state, "update_shared_novel_state", runtime.update_shared_novel_state)
    monkeypatch.setattr(query_service, "get_query_service", lambda: query_service.QueryService(shared))
    signals = []
    monkeypatch.setattr(novel_stop_signal, "publish_start_signal", lambda nid: signals.append(("start", nid)))
    monkeypatch.setattr(novel_stop_signal, "publish_stop_signal", lambda nid: signals.append(("stop", nid)))
    try:
        yield db, repo, shared, signals, queue
    finally:
        queue.stop_consumer()
        pipe.close()
        pipe.join_thread()
        db.close_all()


async def test_stop_repairs_stale_mirror_and_acknowledges_real_stop_once(book):
    db, repo, shared, signals, _ = book
    runtime_state.update_shared_novel_state("book", autopilot_status="stopped", current_stage="writing", autopilot_run_epoch=0)
    response = await routes.stop_autopilot("book")
    assert response["success"]
    stopped = repo.get_by_id(NovelId("book"))
    assert stopped.autopilot_status == AutopilotStatus.STOPPED
    assert stopped.autopilot_run_epoch == response["autopilot_run_epoch"] == 1
    assert shared.get_raw_state("book")["autopilot_run_epoch"] == 1

    duplicate = await routes.stop_autopilot("book")
    assert duplicate["autopilot_run_epoch"] == 1
    assert signals == [("stop", "book")]


async def test_unavailable_writer_never_acknowledges_stop(book):
    db, repo, shared, signals, queue = book
    queue.stop_consumer()
    with pytest.raises(HTTPException) as error:
        await routes.stop_autopilot("book")
    assert error.value.status_code == 503
    assert repo.get_by_id(NovelId("book")).autopilot_status == AutopilotStatus.RUNNING
    assert signals == []


@pytest.mark.parametrize("warm", [True, False])
async def test_resume_uses_displayed_gate_and_clears_only_its_marker(book, monkeypatch, warm):
    db, repo, shared, signals, _ = book
    novel = repo.get_by_id(NovelId("book"))
    novel.autopilot_status = AutopilotStatus.STOPPED
    novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
    other = {"code": "unrelated", "message": "Keep this audit evidence"}
    novel.last_audit_issues = [other, {"code": NARRATIVE_REVIEW_ISSUE, "message": "Check the ending"}]
    with sqlite_writes_bypass_queue():
        repo.save(novel)
    if warm:
        runtime_state.update_shared_novel_state("book", current_stage="paused_for_review", autopilot_status="stopped",
                               narrative_review_reason="Check the ending", active_invocation_session_id="stale",
                               active_invocation_status="failed", macro_structure_ready=False)
    monkeypatch.setattr(routes, "_has_chapter_nodes_under_current_act", lambda *_: False)
    monkeypatch.setattr(routes, "_macro_structure_exists", lambda *_: False)
    before = await routes.get_autopilot_status("book")
    assert before["review_gate"]["can_resume"] and before["review_gate"]["message"] == "Check the ending"
    result = await routes.resume_from_review("book")
    assert result["autopilot_run_epoch"] == 1
    saved = repo.get_by_id(novel.novel_id)
    assert saved.autopilot_status == AutopilotStatus.RUNNING
    assert saved.last_audit_issues == [other]
    assert shared.get_raw_state("book")["narrative_review_reason"] == ""
    assert signals == [("start", "book")]


@pytest.mark.parametrize("failure", ["conflict", "cleanup"])
def test_start_cleanup_requires_claim_and_interrupted_claim_can_retry(book, monkeypatch, failure):
    db, repo, shared, signals, _ = book
    decision = AutopilotRecoveryDecision(novel_id="book", next_stage="writing", discard_transient_invocations=True)
    cleanups = []
    def decide(self, novel_id):
        if failure == "conflict":
            routes._submit_control_update(
                "UPDATE novels SET autopilot_run_epoch=1 WHERE id=? RETURNING autopilot_run_epoch", ["book"]
            )
        return decision
    def cleanup(self, decision):
        saved = repo.get_by_id(NovelId("book"))
        cleanups.append((saved.autopilot_status, saved.active_pipeline_run_id))
        if len(cleanups) == 1:
            raise RuntimeError("cleanup interrupted")
    monkeypatch.setattr(AutopilotRecoveryPolicy, "decide_on_start", decide)
    monkeypatch.setattr(AutopilotRecoveryPolicy, "apply_transient_cleanup", cleanup)
    kwargs = {"max_auto_chapters": 9, "target_chapters": None, "target_words_per_chapter": None}
    if failure == "conflict":
        with pytest.raises(HTTPException) as error:
            routes._persist_autopilot_running_sync("book", **kwargs)
        assert error.value.status_code == 409
        assert not cleanups
        assert repo.get_by_id(NovelId("book")).autopilot_status == AutopilotStatus.RUNNING
    else:
        with pytest.raises(RuntimeError, match="cleanup interrupted"):
            routes._persist_autopilot_running_sync("book", **kwargs)
        assert cleanups[0][0] == AutopilotStatus.STOPPED
        assert cleanups[0][1]
        assert repo.get_by_id(NovelId("book")).autopilot_status == AutopilotStatus.STOPPED
        assert routes._persist_autopilot_running_sync("book", **kwargs)["run_epoch"] == 1
        assert cleanups[1][1] != cleanups[0][1]
        assert repo.get_by_id(NovelId("book")).autopilot_status == AutopilotStatus.RUNNING


async def test_guard_stop_committed_ahead_of_manual_stop_is_idempotent(book, monkeypatch):
    _, repo, _, signals, _ = book
    submit = routes._submit_control_update

    def guard_then_stop(sql, params):
        submit("""UPDATE novels SET autopilot_status='stopped', current_stage='paused_for_review'
                  WHERE id=? RETURNING autopilot_run_epoch""", ["book"])
        return submit(sql, params)

    monkeypatch.setattr(routes, "_submit_control_update", guard_then_stop)
    response = await routes.stop_autopilot("book")
    saved = repo.get_by_id(NovelId("book"))
    assert saved.current_stage == NovelStage.PAUSED_FOR_REVIEW
    assert response["autopilot_run_epoch"] == saved.autopilot_run_epoch == 0
    assert signals == []
