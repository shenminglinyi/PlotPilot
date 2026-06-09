import pytest

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext


class _Pipeline(BaseStoryPipeline):
    pass


@pytest.mark.asyncio
async def test_score_tension_does_not_write_default_when_missing_multidimensional_score():
    pipeline = _Pipeline()
    ctx = PipelineContext(
        novel_id="novel-1",
        chapter_number=3,
        chapter_content="正文",
    )

    result = await pipeline._step_score_tension(ctx)

    assert result.passed is True
    assert ctx.tension_composite is None


@pytest.mark.asyncio
async def test_score_tension_keeps_multidimensional_score():
    pipeline = _Pipeline()
    ctx = PipelineContext(novel_id="novel-1", chapter_number=3)
    ctx.tension_composite = 73.0

    result = await pipeline._step_score_tension(ctx)

    assert result.passed is True
    assert ctx.tension_composite == 73.0
