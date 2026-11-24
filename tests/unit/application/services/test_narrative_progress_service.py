from unittest.mock import AsyncMock, Mock

import pytest

from application.blueprint.services.narrative_progress_service import NarrativeProgressService
from domain.novel.entities.novel import Novel
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType, StoryNode


def service_fixture():
    volume = StoryNode('v','n',NodeType.VOLUME,1,'结局卷',0)
    chapter = StoryNode('c','n',NodeType.CHAPTER,1,'正文',0,parent_id='v')
    def store_review(novel_id, volume_id, contract, expected):
        volume.metadata['narrative_progress'] = contract
    repo=Mock(get_by_novel=AsyncMock(return_value=[volume,chapter]),
              commit_narrative_review=AsyncMock(side_effect=store_review))
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
    service.nodes.commit_narrative_review.assert_awaited_once()
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
    service.nodes.commit_narrative_review.assert_not_awaited()
    assert volume.metadata == {}


@pytest.mark.asyncio
async def test_foreign_novel_volume_cannot_be_reviewed():
    service,volume=service_fixture()
    volume.novel_id='other'
    with pytest.raises(LookupError):
        await service.save_review('n','v',{'chapter_budget':1})
    service.nodes.commit_narrative_review.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_ending_binds_last_chapter_even_if_all_citations_are_earlier():
    service, volume = service_fixture()
    service.novels.get_by_id.return_value.target_chapters = 3
    chapters = [StoryNode(f'c{n}', 'n', NodeType.CHAPTER, n, f'第{n}章', n, parent_id='v')
                for n in range(1, 4)]
    service.nodes.get_by_novel.return_value = [volume, *chapters]
    revisions = {1: 'r1', 2: 'r2', 3: 'r3'}
    service.chapters.completed_revisions.return_value = revisions
    item = {'id': 'decision', 'description': '作出选择', 'status': 'resolved', 'evidence_chapters': [1]}
    ending = {'reviewed_through_chapter': 3, 'core_conflict': item, 'character_outcomes': item,
              'ending': item, 'open_ending_notes': ['门外的来人有意留白']}
    report = await service.save_review('n', 'v', {'milestones': [item], 'ending_review': ending})
    assert report['story_finished']
    assert volume.metadata['narrative_progress']['ending_review']['reviewed_through_revision'] == 'r3'

    revisions[2] = 'uncited chapter rewritten'
    assert (await service.get_report('n'))['story_finished']
    revisions[3] = 'last chapter rewritten'
    report = await service.save_review('n', 'v', {'goal': '重新核预算'})
    assert not report['story_finished']
    assert report['volumes'][0]['exit_verified']
    assert any('核读末章' in issue for issue in report['issues'])
    assert (await service.save_review('n', 'v', {'ending_review': ending}))['story_finished']

    del volume.metadata['narrative_progress']['ending_review']['reviewed_through_revision']
    assert not (await service.get_report('n'))['story_finished']
