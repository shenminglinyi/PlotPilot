"""Exercise the daemon's real queued writes against a private SQLite file."""
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.engine.services import persistence_queue as queues
from application.engine.services.query_service import QueryService
from application.engine.services.shared_state_repository import SharedStateRepository, daemon_novel_run
from application.engine.services.state_bootstrap import StateBootstrap
from domain.novel.entities.novel import AutopilotStatus, Novel, NovelStage
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from engine.runtime.daemon_host import DaemonHostMixin
from engine.runtime import audit_delegate
from engine.runtime.narrative_progress_guard import enforce_progress, pause_for_progress
from infrastructure.persistence.database import connection
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from interfaces.runtime import AppRuntime


@pytest.fixture
def daemon_db(tmp_path, monkeypatch):
    path = tmp_path / "plotpilot.db"
    db = connection.DatabaseConnection(str(path))
    monkeypatch.setenv("PLOTPILOT_PROD_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(connection, "get_database", lambda *args: db)
    queue = queues.PersistenceQueue()
    monkeypatch.setattr(queues, "_persistence_queue", queue)
    pipe = queue.initialize()
    queues.register_persistence_handlers()
    consumed = Event()
    queue.register_handler("test_barrier", lambda _: consumed.set())
    queue.start_consumer()

    def drain():
        consumed.clear()
        assert queue.push("test_barrier", {})
        assert consumed.wait(5), "writer did not consume pending commands"
        assert queue.get_stats()["failed"] == 0

    repo = SqliteNovelRepository(db)
    novel = Novel(NovelId("stop-test"), "Stop test", "fixture", 1,
                  current_stage=NovelStage.WRITING, autopilot_status=AutopilotStatus.RUNNING)
    with sqlite_writes_bypass_queue():
        repo.save(novel)
    host = DaemonHostMixin()
    host.novel_repository = repo
    # Isolate the UI memory mirror. All control reads, SQL and the consumer are real.
    host._update_shared_state = lambda *args, **kwargs: None
    try:
        yield host, novel, db, drain
    finally:
        queue.stop_consumer()
        pipe.close()
        pipe.join_thread()
        db.close_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("reviewed", [False, True])
async def test_guard_stops_survive_queue_and_cold_reload(daemon_db, monkeypatch, reviewed):
    host, novel, db, drain = daemon_db
    report = {"story_finished": reviewed, "issues": [] if reviewed else ["Missing ending evidence"]}
    policy = SimpleNamespace(generation_finished=True, report=lambda: report)
    monkeypatch.setattr("engine.runtime.narrative_progress_guard.progress_policy",
                        AsyncMock(return_value=policy))
    assert await enforce_progress(host, novel)
    # The lifecycle flushes again before the next polling iteration.
    host._merge_autopilot_status_from_db(novel)
    host._save_novel_state(novel)
    drain()
    db.close()
    cold = host.novel_repository.get_by_id(novel.novel_id)
    assert cold.autopilot_status == AutopilotStatus.STOPPED
    assert cold.current_stage == (NovelStage.COMPLETED if reviewed else NovelStage.PAUSED_FOR_REVIEW)
    assert host.novel_repository.find_by_autopilot_status("running") == []
    assert not host._is_still_running(cold)
    if not reviewed:
        assert "Missing ending evidence" in cold.last_audit_issues[-1]["message"]
    shared = SharedStateRepository({})
    query = QueryService(shared)
    # Exercise both /status paths: empty memory and bootstrapped memory.
    for bootstrapped in (False, True):
        if bootstrapped:
            assert StateBootstrap(shared).load_novel(novel.novel_id.value)
        status = query.get_novel_status_dict(novel.novel_id.value)
        assert status["autopilot_status"] == "stopped"
        assert status["current_stage"] == cold.current_stage.value
        if reviewed:
            assert not status.get("review_gate")
        else:
            assert "Missing ending evidence" in status["autopilot_pause_reason"]
            assert status["review_gate"]["message"] == status["autopilot_pause_reason"]


def test_old_tick_cannot_restart_after_manual_stop_or_stop_a_new_run(daemon_db):
    host, novel, db, drain = daemon_db
    host._queue_sql("UPDATE novels SET autopilot_status='stopped' WHERE id=?", [novel.novel_id.value])
    host._save_novel_ephemeral(novel)  # Previously prepared writer snapshot.
    drain()
    assert host.novel_repository.get_by_id(novel.novel_id).autopilot_status == AutopilotStatus.STOPPED

    host._queue_sql("UPDATE novels SET autopilot_status='running', autopilot_run_epoch=1 WHERE id=?",
                    [novel.novel_id.value])
    pause_for_progress(host, novel, "Late stop from run 0")
    drain()
    resumed = host.novel_repository.get_by_id(novel.novel_id)
    assert resumed.autopilot_run_epoch == 1
    assert resumed.autopilot_status == AutopilotStatus.RUNNING
    assert resumed.current_stage == NovelStage.WRITING


@pytest.mark.parametrize("structure_ready", [False, True])
def test_cold_macro_review_matches_bootstrapped_gate(daemon_db, structure_ready):
    host, novel, _, drain = daemon_db
    nid = novel.novel_id.value
    host._queue_sql("UPDATE novels SET current_stage='paused_for_review', autopilot_run_epoch=3 WHERE id=?", [nid])
    if structure_ready:
        host._queue_sql(
            "INSERT INTO story_nodes(id, novel_id, node_type, number, title, order_index) "
            "VALUES ('volume-1', ?, 'volume', 1, 'Volume I', 0)", [nid])
    drain()
    shared = SharedStateRepository({})
    query = QueryService(shared)
    cold = query.get_novel_status_dict(nid)
    assert StateBootstrap(shared).load_novel(nid)
    warm = query.get_novel_status_dict(nid)
    assert cold["autopilot_run_epoch"] == warm["autopilot_run_epoch"] == 3
    for status in (cold, warm):
        assert status["review_gate"]["type"] == "macro_plan"
        assert status["review_gate"]["can_resume"] is structure_ready


def test_old_tick_cannot_replace_new_run_in_process_shared_status(daemon_db, monkeypatch):
    host, novel, _, drain = daemon_db
    del host._update_shared_state  # Exercise the real daemon and API mirror writers.
    runtime = AppRuntime()
    shared = runtime.get_shared_state()
    monkeypatch.setitem(sys.modules, "__shared_state", shared)
    nid = novel.novel_id.value
    try:
        host._queue_sql("UPDATE novels SET autopilot_run_epoch=1 WHERE id=?", [nid])
        drain()
        runtime.update_shared_novel_state(nid, autopilot_status="running", current_stage="writing",
                                          autopilot_run_epoch=1, autopilot_pause_reason="")
        pause_for_progress(host, novel, "Delayed review from run 0")
        with daemon_novel_run(nid, 0):
            host._update_shared_state(nid, current_stage="auditing", writing_substep="old")
        drain()
        novel.autopilot_status = AutopilotStatus.RUNNING  # In-flight worker from run 0.
        assert not host._is_still_running(novel)
        snapshot = QueryService(SharedStateRepository(shared)).get_novel_status_dict(nid)
        assert snapshot["autopilot_status"] == "running"
        assert snapshot["current_stage"] == "writing"
        assert snapshot["autopilot_run_epoch"] == 1
        assert not snapshot["autopilot_pause_reason"]
        assert not runtime.get_shared_novel_state(nid).get("writing_substep")
        assert host.novel_repository.get_by_id(novel.novel_id).autopilot_status == AutopilotStatus.RUNNING
        runtime.update_shared_novel_state(nid, autopilot_status="stopped", current_stage="paused_for_review",
                                          autopilot_run_epoch=1, autopilot_pause_reason="Current review")
        runtime.update_shared_novel_state(nid, autopilot_status="running", current_stage="writing",
                                          autopilot_run_epoch=1, autopilot_pause_reason="")
        assert runtime.get_shared_novel_state(nid)["autopilot_pause_reason"] == "Current review"
    finally:
        runtime._mp_manager.shutdown()


@pytest.mark.asyncio
async def test_last_chapter_audit_publishes_review_and_skips_post_stop_generation(daemon_db, monkeypatch):
    host, novel, db, drain = daemon_db
    host.chapter_repository = SqliteChapterRepository(db)
    host.story_node_repo = StoryNodeRepository(db)
    content = "A final chapter without evidence for the ending."
    with sqlite_writes_bypass_queue():
        host.chapter_repository.save(Chapter("last-chapter", novel.novel_id, 1, "End",
                                             content=content, status=ChapterStatus.COMPLETED))
        db.commit()
    novel.auto_approve_mode = True
    host.aftermath_pipeline = None
    host._score_voice_only = AsyncMock(return_value={})
    host._apply_voice_rewrite_loop = AsyncMock(return_value=(content, {}))
    host._legacy_auditing_tasks_and_voice = Mock(return_value={})
    host._run_anti_ai_audit = AsyncMock(return_value=None)
    host._publish_audit_event = Mock()
    host._extract_chapter_bridge = AsyncMock()
    host._sync_chronicles_to_shared_memory = Mock()
    host._sync_storylines_to_shared_memory = Mock()
    monkeypatch.setattr(audit_delegate, "_consume_pending_payload", lambda *a, **kw: {})
    monkeypatch.setattr(audit_delegate, "_read_shared_state", lambda _: {})
    monkeypatch.setattr(audit_delegate, "_write_autopilot_invocation_input", lambda **kw: None)
    await audit_delegate.run_chapter_audit(host, novel)
    drain()
    events = [call.args[2] for call in host._publish_audit_event.call_args_list
              if call.args[1] == "audit_complete"]
    assert len(events) == 1
    assert events[0]["is_completed"] is False and events[0]["paused_for_review"] is True
    cold = host.novel_repository.get_by_id(novel.novel_id)
    assert (cold.current_stage, cold.autopilot_status) == (NovelStage.PAUSED_FOR_REVIEW, AutopilotStatus.STOPPED)
    host._extract_chapter_bridge.assert_not_awaited()
