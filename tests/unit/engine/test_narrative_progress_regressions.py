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
    repo = Mock()
    repo.get_by_id = AsyncMock(side_effect=lambda key: {'a1': previous, 'v2': destination}.get(key))
    repo.save = AsyncMock()
    service = ContinuousPlanningService(repo, Mock(), Mock())
    service._get_bible_context = Mock(return_value={})
    service._generate_next_act_info = AsyncMock(return_value={
        'title': '新的政治选择', 'description': '推进下一卷', 'suggested_chapter_count': 9})

    await service.create_next_act_auto('n1', 'a1', target_volume_id='v2', chapter_budget=2)

    created = repo.save.call_args.args[0]
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
