import multiprocessing as mp
from unittest.mock import AsyncMock, Mock

import pytest

from application.engine.services import persistence_queue as queues
from application.engine.services.checked_chapter_write import submit_checked_chapter
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.narrative_progress import NarrativeProgressError
from domain.structure.story_node import NodeType, StoryNode
from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.runtime.writing_delegate import _prepare_writing_session, run_writing
from engine.runtime.daemon_host import DaemonHostMixin
from infrastructure.persistence.database import connection
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue


@pytest.fixture
def short_book(tmp_path, monkeypatch):
    db = connection.DatabaseConnection(str(tmp_path / "plotpilot.db"))
    monkeypatch.setattr(connection, "get_database", lambda *args: db)
    novel = Novel(NovelId("book"), "Test", "Test", 4, current_stage=NovelStage.WRITING,
                  autopilot_status=AutopilotStatus.RUNNING, last_audit_chapter_number=2)
    host = Mock()
    host.chapter_repository = SqliteChapterRepository(db)
    host.story_node_repo = StoryNodeRepository(db)
    host.novel_repository = SqliteNovelRepository(db)
    with sqlite_writes_bypass_queue():
        host.novel_repository.save(novel)
        for number in [1, 2]:
            volume, act = f"v{number}", f"a{number}"
            host.story_node_repo.save_sync(StoryNode(volume,"book",NodeType.VOLUME,number,volume,number))
            host.story_node_repo.save_sync(StoryNode(act,"book",NodeType.ACT,number,act,number,parent_id=volume))
            for n in (number * 2 - 1, number * 2):
                host.story_node_repo.save_sync(StoryNode(f"c{n}","book",NodeType.CHAPTER,n,f"章{n}",n,
                                                         parent_id=act,outline=f"Outline {n}"))
        for n, content in [(1, "Drafted."), (2, "")]:
            host.chapter_repository.save(Chapter(f"manuscript-{n}", novel.novel_id, n, f"章{n}",
                                                 content=content, status=ChapterStatus.COMPLETED))
        db.commit()
    queue = queues.PersistenceQueue()
    pipe = queue.initialize()
    monkeypatch.setattr(queues, "_persistence_queue", queue)
    queues.register_persistence_handlers()
    queue.start_consumer()
    try:
        yield host, novel, pipe
    finally:
        queue.stop_consumer()
        pipe.close()
        pipe.join_thread()
        db.close_all()


@pytest.mark.parametrize("mode", [True, False])
async def test_both_writers_receive_the_same_checked_empty_audited_chapter(short_book, monkeypatch, mode):
    host, novel, _ = short_book
    host.use_story_pipeline_for_writing = mode
    generate = AsyncMock()
    monkeypatch.setattr("engine.runtime.writing_delegate.run_story_pipeline_writing", generate)
    monkeypatch.setattr("engine.runtime.legacy_writing_delegate.run_legacy_writing", generate)
    await run_writing(host,novel)
    session = generate.await_args.kwargs["session"]
    assert (session.target.volume_id, session.target.act_id, session.target.chapter_id) == ("v1", "a1", "c2")
    ctx = PipelineContext(novel_id="book", writing_session=session, chapter_repository=host.chapter_repository)
    pipeline = BaseStoryPipeline()
    assert (await pipeline._step_find_next_chapter(ctx)).passed
    assert ctx.chapter_number == 2 and ctx.outline == "Outline 2"
    ctx.chapter_content = "Recovered chapter."
    assert (await pipeline._step_save_chapter(ctx)).passed
    assert host.chapter_repository.get_by_novel_and_number(novel.novel_id, 2).content == ctx.chapter_content
    assert host.chapter_repository.get_by_novel_and_number(novel.novel_id, 3) is None
    # A retry may not overwrite the accepted manuscript or cross the volume gate.
    with pytest.raises(NarrativeProgressError):
        session.submit("completed", content="duplicate")
    generate.reset_mock()
    await run_writing(host,novel)
    generate.assert_not_awaited()
    assert novel.current_stage == NovelStage.PAUSED_FOR_REVIEW


@pytest.mark.parametrize("edit", ["plan", "draft"])
async def test_checked_save_refuses_a_concurrent_edit(short_book, edit):
    host, novel, _ = short_book
    session = await _prepare_writing_session(host, novel)
    session.submit("preplan", outline="Generated plan", preplan={"chapter_plan": "beats"})
    db = host.chapter_repository.db
    with sqlite_writes_bypass_queue():
        if edit == "plan":
            from application.blueprint.services.story_structure_service import StoryStructureService
            service = StoryStructureService(host.story_node_repo)
            with pytest.raises(ValueError, match="Node not found"):
                await service.update_node("c2", "different-book", title="Wrong book")
            changed = await service.update_node("c2", "book", title="Changed by the author")
            assert changed["outline"] == "Generated plan"
            assert changed["metadata"]["chapter_preplan"] == {"chapter_plan": "beats"}
        else:
            db.execute("UPDATE chapters SET content='Author draft',status='draft' WHERE novel_id='book' AND number=2")
        db.commit()
    with pytest.raises(NarrativeProgressError):
        session.submit("completed", content="Generated old prose")
    saved = host.chapter_repository.get_by_novel_and_number(novel.novel_id, 2)
    assert saved.content == ("" if edit == "plan" else "Author draft")


def _daemon_commit(queue, reply, binding):
    queues.inject_persistence_queue(queue)
    try:
        result = submit_checked_chapter(binding, "completed", content="Cross-process chapter")
        reply.send(result)
    finally:
        reply.close()


async def test_daemon_waits_for_actual_writer_commit(short_book):
    host, novel, pipe = short_book
    session = await _prepare_writing_session(host, novel)
    context = mp.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_daemon_commit, args=(pipe, send, session.binding()))
    process.start()
    send.close()
    try:
        assert receive.poll(20)
        assert receive.recv()["word_count"] == len("Cross-process chapter")
        assert host.chapter_repository.get_by_novel_and_number(novel.novel_id, 2).content == "Cross-process chapter"
        process.join(timeout=10)
        assert process.exitcode == 0
    finally:
        receive.close()
        if process.is_alive():
            process.terminate()
            process.join()


async def test_delayed_approval_cannot_revive_manually_stopped_run(short_book):
    host, novel, _ = short_book
    session = await _prepare_writing_session(host, novel)
    db = host.chapter_repository.db
    with sqlite_writes_bypass_queue():
        db.execute("UPDATE novels SET autopilot_status='stopped',autopilot_run_epoch=1 WHERE id='book'")
        db.commit()
    with pytest.raises(NarrativeProgressError):
        submit_checked_chapter(session.binding(), "adopt_beat", content="Late", next_beat_index=1)
    assert host.chapter_repository.get_by_novel_and_number(novel.novel_id, 2).content == ""
    assert host.novel_repository.get_by_id(novel.novel_id).autopilot_status == AutopilotStatus.STOPPED


async def test_gap_commit_chooses_exact_chapter_for_audit_after_restart(short_book):
    host, novel, _ = short_book
    db = host.chapter_repository.db
    audit = DaemonHostMixin()
    audit.chapter_repository = host.chapter_repository
    with sqlite_writes_bypass_queue():
        host.chapter_repository.save(Chapter("later", novel.novel_id, 4, "Later", content="Later.",
                                             status=ChapterStatus.COMPLETED))
        db.commit()
    assert audit._count_completed_chapters(novel.novel_id) == 2
    session = await _prepare_writing_session(host, novel)
    session.submit("completed", content="Fill the gap.")
    db.close()
    assert audit._latest_completed_chapter_number(novel.novel_id) == 2
    assert audit._count_completed_chapters(novel.novel_id) == 3
    assert db.fetch_one("SELECT current_stage FROM novels WHERE id='book'")["current_stage"] == "auditing"
    from application.engine.services.autopilot_recovery_policy import AutopilotRecoveryPolicy
    with sqlite_writes_bypass_queue():
        db.execute("UPDATE novels SET current_stage='writing' WHERE id='book'")
        db.commit()
    decision = AutopilotRecoveryPolicy(db).decide_on_daemon_tick(novel)
    assert (decision.next_stage, decision.chapter_number) == ("auditing", 2)


async def test_concurrent_nonempty_draft_edit_then_undo_invalidates_started_generation(short_book):
    host, novel, _ = short_book
    db = host.chapter_repository.db
    with sqlite_writes_bypass_queue():
        db.execute("UPDATE chapters SET status='draft',content='prior' WHERE novel_id='book' AND number=2")
        db.commit()
    session = await _prepare_writing_session(host, novel)
    with sqlite_writes_bypass_queue():
        for text in ("later", "prior"):
            db.execute("UPDATE chapters SET content=? WHERE novel_id='book' AND number=2", (text,))
        db.commit()
    with pytest.raises(NarrativeProgressError):
        session.submit("completed", content="Old output")
