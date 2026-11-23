from unittest.mock import AsyncMock, Mock

import pytest

from domain.novel.entities.novel import AutopilotStatus, Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType, StoryNode
from engine.runtime.narrative_progress_guard import enforce_progress
from engine.runtime.writing_delegate import run_writing


def host_and_novel():
    volume = StoryNode('v1','n',NodeType.VOLUME,1,'卷一',0)
    act = StoryNode('a1','n',NodeType.ACT,1,'幕一',0,parent_id='v1')
    nodes = [volume, act] + [StoryNode(f'c{n}','n',NodeType.CHAPTER,n,'章',n,parent_id='a1') for n in (1,2)]
    host = Mock()
    host.story_node_repo.get_by_novel = AsyncMock(return_value=nodes)
    host.chapter_repository.completed_revisions.return_value = {1:'r1',2:'r2'}
    novel = Novel(NovelId('n'),'小说','作者',2,current_auto_chapters=2,
                  current_stage=NovelStage.WRITING,autopilot_status=AutopilotStatus.RUNNING,
                  auto_approve_mode=True)
    return host, novel, volume


@pytest.mark.asyncio
@pytest.mark.parametrize('pipeline_mode', [True,False])
async def test_both_modes_stop_at_target_without_generating_extra_chapter(pipeline_mode,monkeypatch):
    host, novel, _ = host_and_novel()
    host.use_story_pipeline_for_writing = pipeline_mode
    writer = AsyncMock()
    monkeypatch.setattr('engine.runtime.writing_delegate.run_story_pipeline_writing',writer)
    monkeypatch.setattr('engine.runtime.legacy_writing_delegate.run_legacy_writing',writer)
    await run_writing(host,novel)
    writer.assert_not_awaited()
    assert novel.current_stage == NovelStage.PAUSED_FOR_REVIEW
    assert novel.autopilot_status == AutopilotStatus.STOPPED
    assert novel.last_audit_issues[-1]['code'] == 'narrative_progress_review_required'


@pytest.mark.asyncio
async def test_valid_manuscript_backed_review_completes_without_new_generation():
    host, novel, volume = host_and_novel()
    item={'id':'goal','description':'结局','status':'resolved','evidence_chapters':[2],
          'evidence_revisions':{'2':'r2'}}
    volume.metadata={'narrative_progress':{'chapter_budget':2,'milestones':[item],
        'ending_review':{'reviewed_through_chapter':2,'core_conflict':item,
                         'character_outcomes':item,'ending':item}}}
    assert await enforce_progress(host,novel,writing=True)
    assert novel.current_stage == NovelStage.COMPLETED
    assert novel.autopilot_status == AutopilotStatus.STOPPED


@pytest.mark.asyncio
async def test_unreadable_manuscript_stops_instead_of_assuming_completion():
    host, novel, _ = host_and_novel()
    host.chapter_repository.completed_revisions.side_effect=RuntimeError('读取失败')
    assert await enforce_progress(host,novel,writing=True)
    assert novel.current_stage == NovelStage.PAUSED_FOR_REVIEW
    assert novel.autopilot_status == AutopilotStatus.STOPPED


@pytest.mark.asyncio
async def test_resuming_legacy_completed_book_rechecks_closure_instead_of_spinning_running(monkeypatch):
    from engine.runtime.novel_lifecycle import process_novel
    host, novel, _ = host_and_novel()
    novel.current_stage=NovelStage.COMPLETED
    host._is_still_running.return_value=True
    await process_novel(host,novel)
    assert novel.current_stage == NovelStage.PAUSED_FOR_REVIEW
    assert novel.autopilot_status == AutopilotStatus.STOPPED
