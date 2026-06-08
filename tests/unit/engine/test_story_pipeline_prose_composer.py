from __future__ import annotations

import pytest

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.pipeline.prose_composer import ChapterProseInvocationComposer, ProseCompositionRequest, ProseCompositionResult


class _Pipeline(BaseStoryPipeline):
    pass


class _Composer:
    def __init__(self, result: ProseCompositionResult):
        self.result = result
        self.requests = []

    async def compose(self, request):
        self.requests.append(request)
        if request.stream_sink:
            request.stream_sink(self.result.content)
        return self.result


def test_chapter_prose_composer_builds_only_core_prompt_variables():
    composer = ChapterProseInvocationComposer()
    request = ProseCompositionRequest(
        novel_id="novel-1",
        chapter_number=4,
        outline="七段细纲",
        context_text="前3章规划",
        target_words=2000,
        metadata={
            "key_plot_points": ["情节点1", "情节点2"],
            "chapter_characters": ["林渊", "林晚"],
            "chapter_plan_json": {"unused": True},
            "previous_summary": "不应进入 prompt",
            "previous_ending": "不应进入 prompt",
        },
    )

    variables = composer._build_variables(request)

    assert variables == {
        "target_words": 2000,
        "chapter_outline": "七段细纲",
        "continuity_context": "前3章规划",
    }


@pytest.mark.asyncio
async def test_story_pipeline_uses_chapter_prose_composer_for_auto_approved_flow():
    composer = _Composer(ProseCompositionResult(content="整章正文"))
    pipeline = _Pipeline()
    ctx = PipelineContext(
        novel_id="novel-composer",
        chapter_number=3,
        outline="本章大纲",
        context_text="世界观上下文",
        target_word_count=2400,
        auto_approve_mode=True,
    )
    ctx.llm_service = object()
    ctx.prose_composer = composer

    result = await pipeline._step_generate(ctx)

    assert result.passed
    assert ctx.chapter_content == "整章正文"
    assert ctx.word_count == len("整章正文")
    assert composer.requests[0].outline == "本章大纲"
    assert composer.requests[0].context_text == "世界观上下文"


@pytest.mark.asyncio
async def test_story_pipeline_marks_awaiting_review_from_composer():
    composer = _Composer(ProseCompositionResult(awaiting_review=True, session_id="session-1"))
    pipeline = _Pipeline()
    ctx = PipelineContext(
        novel_id="novel-review",
        chapter_number=1,
        outline="本章大纲",
        auto_approve_mode=True,
    )
    ctx.llm_service = object()
    ctx.prose_composer = composer

    result = await pipeline._step_generate(ctx)

    assert not result.passed
    assert result.message == "awaiting_ai_review"
    assert ctx.metadata["awaiting_ai_review"] is True
    assert ctx.metadata["active_invocation_session_id"] == "session-1"
