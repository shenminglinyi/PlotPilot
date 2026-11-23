from unittest.mock import AsyncMock, Mock

import pytest

from application.blueprint.services.narrative_progress_service import NarrativeProgressService
from domain.novel.entities.novel import Novel
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType, StoryNode


def service_fixture():
    volume = StoryNode('v','n',NodeType.VOLUME,1,'结局卷',0)
    chapter = StoryNode('c','n',NodeType.CHAPTER,1,'正文',0,parent_id='v')
    repo=Mock(get_by_id=AsyncMock(return_value=volume),
              get_by_novel=AsyncMock(return_value=[volume,chapter]),update=AsyncMock())
    chapters=Mock()
    chapters.completed_revisions.return_value={1:'revision-1'}
    novels=Mock()
    novels.get_by_id.return_value=Novel(NovelId('n'),'小说','作者',1)
    return NarrativeProgressService(repo,chapters,novels),volume


@pytest.mark.asyncio
async def test_review_binds_to_committed_revision_and_persists_metadata():
    service,volume=service_fixture()
    await service.save_review('n','v',{'chapter_budget':1,'milestones':[
        {'id':'g','description':'关键冲突','status':'resolved','evidence_chapters':[1]}]})
    item=volume.metadata['narrative_progress']['milestones'][0]
    assert item['evidence_revisions']=={'1':'revision-1'}
    service.nodes.update.assert_awaited_once_with(volume)
    service.chapters.completed_revisions.return_value={1:'edited'}
    report=await service.get_report('n')
    assert report['story_finished'] is False
    assert any('证据已失效' in i for i in report['issues'])


@pytest.mark.asyncio
@pytest.mark.parametrize('evidence', [[2],[],[True]])
async def test_planning_empty_and_boolean_refs_are_rejected_before_writing(evidence):
    service,volume=service_fixture()
    with pytest.raises(ValueError):
        await service.save_review('n','v',{'milestones':[
            {'id':'g','description':'冲突','status':'resolved','evidence_chapters':evidence}]})
    service.nodes.update.assert_not_awaited()
    assert volume.metadata == {}


@pytest.mark.asyncio
async def test_foreign_novel_volume_cannot_be_reviewed():
    service,volume=service_fixture()
    volume.novel_id='other'
    with pytest.raises(LookupError):
        await service.save_review('n','v',{'chapter_budget':1})
    service.nodes.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_budget_edit_does_not_silently_renew_old_assessment():
    service,volume=service_fixture()
    volume.metadata={'narrative_progress':{'chapter_budget':1,'milestones':[
        {'id':'g','description':'冲突','status':'resolved','evidence_chapters':[1],
         'evidence_revisions':{'1':'old-revision'}}]}}
    report=await service.save_review('n','v',{'goal':'重新核查'})
    assert report['volumes'][0]['exit_verified'] is False
    assert volume.metadata['narrative_progress']['milestones'][0]['evidence_revisions']=={'1':'old-revision'}


@pytest.mark.asyncio
async def test_clearing_old_ending_review_returns_unfinished_without_crashing():
    service,volume=service_fixture()
    volume.metadata={'narrative_progress':{'ending_review':{'reviewed_through_chapter':1}}}
    report=await service.save_review('n','v',{'ending_review':None})
    assert report['generation_finished'] is True
    assert report['story_finished'] is False
