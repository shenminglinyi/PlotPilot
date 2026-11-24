"""Manual and automatic continuation against a fresh two-volume, six-chapter database."""
import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from application.blueprint.services.continuous_planning_service import ContinuousPlanningService
from application.blueprint.services.narrative_progress_service import NarrativeProgressService
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.entities.novel import Novel
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.narrative_progress import NarrativeProgressError
from domain.structure.story_node import NodeType, StoryNode
from domain.structure.writing_target import plan_revision
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from interfaces.api.v1.blueprint.continuous_planning_routes import create_next_act


@pytest.fixture
def planning(tmp_path):
    db = DatabaseConnection(str(tmp_path / "book.db"))
    book = Novel(NovelId("book"), "Book", "Author", 6)
    novels, chapters, nodes = SqliteNovelRepository(db), SqliteChapterRepository(db), StoryNodeRepository(db)
    with sqlite_writes_bypass_queue():
        novels.save(book)
        for seq in (1, 2):
            nodes.save_sync(StoryNode(f"v{seq}", "book", NodeType.VOLUME, seq, f"Volume {seq}", seq,
                                      metadata={"narrative_progress": {"chapter_budget": 3}}))
        nodes.save_sync(StoryNode("a1", "book", NodeType.ACT, 1, "Start", 0, parent_id="v1"))
        for seq in (1, 2, 3):
            nodes.save_sync(StoryNode(f"n{seq}", "book", NodeType.CHAPTER, seq, f"Chapter {seq}", seq, parent_id="a1"))
            chapters.save(Chapter(f"c{seq}", book.novel_id, seq, "Chapter", content=f"Written {seq}",
                                  status=ChapterStatus.COMPLETED))
        db.commit()
        service = ContinuousPlanningService(nodes, Mock(), None, chapter_repository=chapters, novel_repository=novels)
        service._generate_next_act_info = AsyncMock(return_value={"title": "Next", "description": "Change",
                                                                  "suggested_chapter_count": 9})
        service._write_chapter_plan_variables = Mock()
        try:
            yield service, db
        finally:
            db.close_all()


async def approve_first(service):
    reviews = NarrativeProgressService(service.story_node_repo, service.chapter_repository, service.novel_repository)
    await reviews.save_review("book", "v1", {"milestones": [{"id": "choice", "description": "Choice",
                              "status": "resolved", "evidence_chapters": [3]}]})


async def test_public_suggestion_and_creation_use_real_chapters_and_share_volume_decision(planning):
    service, _ = planning
    held = await service.continue_planning("book", 3)
    assert not held["suggest_create_next"]
    with pytest.raises(HTTPException) as error:
        await create_next_act("a1", service)
    assert error.value.status_code == 409
    service._generate_next_act_info.assert_not_awaited()

    await approve_first(service)
    ready = await service.continue_planning("book", 3)
    assert (ready["target_volume_id"], ready["chapter_budget"]) == ("v2", 3)
    created = await create_next_act("a1", service, ready["plan_revision"])
    retried = await create_next_act("a1", service, ready["plan_revision"])
    assert created["created"] and not retried["created"]
    assert created["next_act"]["id"] == retried["next_act"]["id"]
    assert created["next_act"]["parent_id"] == "v2"
    assert created["next_act"]["suggested_chapter_count"] == 3
    service._generate_next_act_info.assert_awaited_once()


async def test_empty_completed_chapter_prevents_creating_successor(planning):
    service, db = planning
    db.get_connection().execute("UPDATE chapters SET content='' WHERE number=2")
    db.get_connection().commit()
    result = await service.continue_planning("book", 3)
    assert result["current_act"]["id"] == "a1" and result["progress"] == "2/3"
    with pytest.raises(NarrativeProgressError, match="第2章"):
        await service.create_next_act_auto("book", "a1")
    service._generate_next_act_info.assert_not_awaited()


async def test_concurrent_request_and_replanned_destination_do_not_commit(planning):
    service, _ = planning
    await approve_first(service)
    waiting, resume = asyncio.Event(), asyncio.Event()
    async def generate(*args):
        waiting.set()
        await resume.wait()
        return {"title": "Obsolete", "description": "No longer valid"}
    service._generate_next_act_info.side_effect = generate
    attempt = asyncio.create_task(service.create_next_act_auto("book", "a1"))
    await waiting.wait()
    try:
        with pytest.raises(NarrativeProgressError, match="正在生成"):
            await service.create_next_act_auto("book", "a1")
        volume = await service.story_node_repo.get_by_id("v2")
        volume.description = "New direction"
        await service.story_node_repo.update(volume)
    finally:
        resume.set()
    with pytest.raises(NarrativeProgressError, match="大纲或正文已变化"):
        await attempt
    assert [n.id for n in await service.story_node_repo.get_by_novel("book") if n.node_type == NodeType.ACT] == ["a1"]
    service._generate_next_act_info.assert_awaited_once()


async def test_approved_plan_is_inserted_atomically_without_deleting_existing_rows(planning):
    service, db = planning
    await approve_first(service)
    act = (await service.create_next_act_auto("book", "a1"))["next_act"]["id"]
    row = {"number": 1, "title": "Choice", "main_event": "Decide",
           "handoff_from_previous": "Evidence", "handoff_to_next": "Consequence"}
    stamp = plan_revision(service._continuation_policy("book"))
    db.get_connection().execute("""INSERT INTO chapters(id,novel_id,number,title,content,status)
                                     VALUES ('other','book',4,'Draft','Retain this draft','draft')""")
    db.get_connection().commit()
    with pytest.raises(NarrativeProgressError, match="已有书稿"):
        await service.confirm_act_planning(act, [row], expected_revision=stamp)
    assert not service.story_node_repo.get_children_sync(act)
    assert db.fetch_one("SELECT content FROM chapters WHERE id='other'")["content"] == "Retain this draft"
    db.get_connection().execute("DELETE FROM chapters WHERE id='other'")
    db.get_connection().commit()
    assert (await service.confirm_act_planning(act, [row], expected_revision=stamp))["created_chapters"] == 1
    assert db.fetch_one("SELECT content FROM chapters WHERE number=4")["content"] == ""
    with pytest.raises(NarrativeProgressError):
        await service.confirm_act_planning(act, [row], expected_revision=stamp)

async def test_new_act_manual_preview_keeps_budget_and_version_through_confirmation(planning):
    service, _ = planning
    await approve_first(service)
    act_id = (await service.create_next_act_auto("book", "a1"))["next_act"]["id"]
    rows = [{"number": n, "title": f"Choice {n}", "main_event": "Decide",
             "handoff_from_previous": "Evidence", "handoff_to_next": "Consequence"} for n in (1, 2, 3)]
    service._stream_act_plan_llm_text = AsyncMock(return_value=json.dumps({"chapters": rows}))
    service._build_act_planning_prompt = Mock()
    preview = await service.plan_act_chapters(act_id, custom_chapter_count=20)
    assert preview["success"] and preview["plan_revision"]
    prompt_args = service._build_act_planning_prompt.call_args.args
    assert prompt_args[-1] == 3 and prompt_args[1]["target_volume"]["id"] == "v2"
    volume = await service.story_node_repo.get_by_id("v2")
    volume.description = "Revised after preview"
    await service.story_node_repo.update(volume)
    with pytest.raises(NarrativeProgressError, match="大纲或正文已变化"):
        await service.confirm_act_planning(act_id, preview["chapters"], expected_revision=preview["plan_revision"])
    assert not service.story_node_repo.get_children_sync(act_id)

async def test_old_empty_act_preview_cannot_replace_later_draft_and_replanning_keeps_it(planning):
    service, db = planning
    await approve_first(service)
    act = (await service.create_next_act_auto("book", "a1"))["next_act"]["id"]
    row = {"number": 1, "title": "Plan", "main_event": "Choose",
           "handoff_from_previous": "Doubt", "handoff_to_next": "Action"}
    old_revision = plan_revision(service._continuation_policy("book"))
    service.story_node_repo.save_sync(StoryNode("author-plan", "book", NodeType.CHAPTER, 4, "Author",
                                                0, parent_id=act))
    service.chapter_repository.save(Chapter("author-draft", NovelId("book"), 4, "Author",
                                             content="Keep this live draft", status=ChapterStatus.DRAFT))
    db.commit()
    with pytest.raises(NarrativeProgressError, match="第4章已有正文"):
        await service.confirm_act_planning(act, [row], expected_revision=old_revision)
    service._stream_act_plan_llm_text = AsyncMock()
    with pytest.raises(NarrativeProgressError, match="章节编辑器"):
        await service.plan_act_chapters(act)
    service._stream_act_plan_llm_text.assert_not_awaited()
    assert service.chapter_repository.get_by_novel_and_number(NovelId("book"), 4).content == "Keep this live draft"
    assert service.story_node_repo.get_children_sync(act)[0].id == "author-plan"

async def test_fresh_revision_can_edit_unwritten_act_and_retains_unrelated_drafts(planning):
    service, db = planning
    await approve_first(service)
    act = (await service.create_next_act_auto("book", "a1"))["next_act"]["id"]
    row = {"number": 1, "title": "Plan", "main_event": "Choose",
           "handoff_from_previous": "Doubt", "handoff_to_next": "Action"}
    await service.confirm_act_planning(act, [row])
    db.get_connection().execute("""INSERT INTO chapters(id,novel_id,number,title,content,status)
                                     VALUES ('orphan','book',12,'Unfiled','Keep this note','draft')""")
    db.get_connection().commit()
    stamp = plan_revision(service._continuation_policy("book"))
    await service.confirm_act_planning(act, [{**row, "title": "Edited outline"}], expected_revision=stamp)
    assert db.fetch_one("SELECT number,title FROM chapters WHERE number=4") == {"number": 4, "title": "Edited outline"}
    assert db.fetch_one("SELECT content FROM chapters WHERE id='orphan'")["content"] == "Keep this note"
