import pytest
from fastapi import HTTPException

from application.engine.services import persistence_queue as queues
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database import connection
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from interfaces.api.v1.engine import autopilot_routes as routes


def test_resume_commits_stage_and_epoch_once_and_rejects_duplicate(tmp_path, monkeypatch):
    db = connection.DatabaseConnection(str(tmp_path / "plotpilot.db"))
    repo = SqliteNovelRepository(db)
    novel = Novel(NovelId("test"), "Test", "Test", 5, current_stage=NovelStage.PAUSED_FOR_REVIEW)
    with sqlite_writes_bypass_queue():
        repo.save(novel)
    monkeypatch.setattr(routes, "get_novel_repository", lambda: repo)
    monkeypatch.setattr(connection, "get_database", lambda: db)
    queue = queues.PersistenceQueue()
    pipe = queue.initialize()
    monkeypatch.setattr(queues, "_persistence_queue", queue)
    queues.register_persistence_handlers()
    queue.start_consumer()
    try:
        assert routes._persist_autopilot_resume_sync(
            "test", next_stage="act_planning", current_act=2
        ) == 1
        saved = repo.get_by_id(novel.novel_id)
        assert saved.autopilot_run_epoch == 1
        assert saved.current_stage == NovelStage.ACT_PLANNING
        assert saved.current_act == 2
        assert saved.autopilot_status.value == "running"
        with pytest.raises(HTTPException) as error:
            routes._persist_autopilot_resume_sync("test", next_stage="writing", current_act=3)
        assert error.value.status_code == 409
        assert repo.get_by_id(novel.novel_id).autopilot_run_epoch == 1
    finally:
        queue.stop_consumer()
        pipe.close()
        pipe.join_thread()
        db.close_all()
