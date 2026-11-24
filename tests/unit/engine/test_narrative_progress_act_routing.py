from unittest.mock import ANY, AsyncMock, Mock

import pytest

from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType, StoryNode
from engine.runtime.act_planning_delegate import run_act_planning


@pytest.mark.asyncio
async def test_runtime_passes_selected_destination_and_clips_new_act_to_remaining_budget(monkeypatch):
    v1=StoryNode('v1','n',NodeType.VOLUME,1,'落地',0,metadata={'narrative_progress':{
        'chapter_budget':2,'milestones':[{'id':'g','description':'河阴后果','status':'resolved',
            'evidence_chapters':[2],'evidence_revisions':{'2':'r2'}}]}})
    v2=StoryNode('v2','n',NodeType.VOLUME,2,'造势',1,metadata={'narrative_progress':{'chapter_budget':1}})
    previous=StoryNode('a1','n',NodeType.ACT,1,'旧幕',0,parent_id='v1')
    written=[StoryNode(f'c{n}','n',NodeType.CHAPTER,n,'正文',n,parent_id='a1') for n in [1,2]]
    nodes=[v1,v2,previous,*written]
    host=Mock()
    host._is_still_running.return_value=True
    host.story_node_repo.get_by_novel=AsyncMock(side_effect=lambda _:list(nodes))
    host.story_node_repo.get_children_sync.return_value=[]
    host.chapter_repository.completed_revisions.return_value={1:'r1',2:'r2'}

    async def create(**kwargs):
        nodes.append(StoryNode('a2','n',NodeType.ACT,2,'新幕',1,parent_id=kwargs['target_volume_id'],
                               suggested_chapter_count=kwargs['chapter_budget']))
    host.planning_service.create_next_act_auto=AsyncMock(side_effect=create)
    monkeypatch.setattr('engine.runtime.act_planning_delegate._consume_pending_act_plan',lambda *a,**kw:{})
    monkeypatch.setattr('engine.runtime.act_planning_delegate._read_shared_state',lambda _: {'has_active_invocation':True,'active_invocation_session_id':'pending'})
    novel=Novel(NovelId('n'),'小说','作者',3,current_act=1,current_auto_chapters=2,
                current_stage=NovelStage.ACT_PLANNING)

    await run_act_planning(host,novel)

    host.planning_service.create_next_act_auto.assert_awaited_once_with(
        novel_id='n',current_act_id='a1',target_volume_id='v2',chapter_budget=1,expected_plan_revision=ANY)
    assert nodes[-1].parent_id=='v2'
    assert nodes[-1].suggested_chapter_count==1
