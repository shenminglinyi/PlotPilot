from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.blueprint.services.continuous_planning_service import ContinuousPlanningService
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType, StoryNode
from engine.runtime.runner import StoryPipelineRunner


@pytest.mark.asyncio
async def test_next_act_uses_selected_volume_and_its_context_and_remaining_budget():
    previous = StoryNode('a1', 'n1', NodeType.ACT, 1, '河阴', 0, parent_id='v1')
    destination = StoryNode('v2', 'n1', NodeType.VOLUME, 2, '造势', 1,
                            description='走向东西魏分立')
    from contextlib import nullcontext
    source = StoryNode('v1', 'n1', NodeType.VOLUME, 1, '开篇', 0, metadata={'narrative_progress': {
        'chapter_budget': 1, 'milestones': [{'id': 'p', 'status': 'resolved', 'evidence_chapters': [1],
                                           'evidence_revisions': {'1': 'r1'}}]}})
    chapter = StoryNode('c1', 'n1', NodeType.CHAPTER, 1, '第一章', 0, parent_id='a1')
    repo = Mock()
    repo.get_plan_nodes_sync.return_value = [source, previous, chapter, destination]
    repo.claim_act_planning.return_value = nullcontext()
    chapter_repo, novels = Mock(), Mock()
    chapter_repo.completed_revisions.return_value = {1: 'r1'}
    novels.get_by_id.return_value = Novel(NovelId('n1'), 'Book', 'Author', 3)
    service = ContinuousPlanningService(repo, Mock(), Mock(), chapter_repository=chapter_repo, novel_repository=novels)
    service._get_bible_context = Mock(return_value={})
    service._generate_next_act_info = AsyncMock(return_value={
        'title': '新的政治选择', 'description': '推进下一卷', 'suggested_chapter_count': 9})

    await service.create_next_act_auto('n1', 'a1', target_volume_id='v2', chapter_budget=2)

    created = repo.save_sync.call_args.args[0]
    assert created.parent_id == 'v2'
    assert created.suggested_chapter_count == 2
    context = service._generate_next_act_info.call_args.args[2]
    assert context['target_volume']['title'] == '造势'
    assert context['target_volume']['description'] == '走向东西魏分立'


@pytest.mark.parametrize('written,expected', [(0,'opening'),(100,'development'),(200,'convergence'),(240,'finale')])
def test_writing_phase_uses_manuscript_progress_instead_of_runtime_stage(written, expected):
    novel = Novel(NovelId('n1'), '长篇', '作者', 250, current_auto_chapters=written,
                  current_stage=NovelStage.WRITING)
    runner = StoryPipelineRunner(novel_repository=Mock(), llm_service=Mock())
    assert runner._get_novel_phase(novel) == expected
