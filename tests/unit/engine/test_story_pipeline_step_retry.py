from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.pipeline.prose_composer import ProseCompositionResult


class _Pipeline(BaseStoryPipeline):
    pass


class _InterruptedComposer:
    def __init__(self):
        self.requests = []

    async def compose(self, request):
        self.requests.append(request)
        request.stream_sink("半章预览")
        return ProseCompositionResult(content="半章预览", interrupted=True, status="cancelled")


class _Workspace:
    def __init__(self):
        self.previews = {}
        self.discards = []

    def begin(self, novel_id, chapter_number, run_id=None):
        self.previews[(novel_id, chapter_number, run_id)] = ""
        return SimpleNamespace(novel_id=novel_id, chapter_number=chapter_number, run_id=run_id)

    def append_preview(self, novel_id, chapter_number, run_id, content):
        self.previews[(novel_id, chapter_number, run_id)] = content

    def discard(self, novel_id, chapter_number, run_id=None):
        self.discards.append((novel_id, chapter_number, run_id))
        if run_id is None:
            for key in list(self.previews):
                if key[0] == novel_id and key[1] == chapter_number:
                    self.previews.pop(key, None)
        else:
            self.previews.pop((novel_id, chapter_number, run_id), None)


class _StoryNodeRepo:
    async def get_by_novel(self, novel_id):
        return [
            SimpleNamespace(
                node_type=SimpleNamespace(value="chapter"),
                number=1,
                title="第一章",
                description="描述",
                outline="新大纲",
            )
        ]


class _ChapterRepo:
    def get_by_novel_and_number(self, novel_id, number):
        return SimpleNamespace(status="draft", content="旧半章正文", outline="旧大纲")


@pytest.mark.asyncio
async def test_story_pipeline_interrupted_generate_discards_workspace_and_does_not_commit_content():
    workspace = _Workspace()
    composer = _InterruptedComposer()
    ctx = PipelineContext(
        novel_id="novel-retry",
        chapter_number=1,
        outline="本章大纲",
        target_word_count=2000,
        auto_approve_mode=True,
        chapter_generation_workspace=workspace,
    )
    ctx.llm_service = object()
    ctx.prose_composer = composer

    result = await _Pipeline()._step_generate(ctx)

    assert not result.passed
    assert result.message == "interrupted"
    assert ctx.generation_interrupted is True
    assert ctx.chapter_content == ""
    assert workspace.previews == {}
    assert any(run_id for _, _, run_id in workspace.discards)


@pytest.mark.asyncio
async def test_story_pipeline_find_next_chapter_ignores_existing_draft_for_regeneration():
    ctx = PipelineContext(novel_id="novel-retry")
    ctx.story_node_repo = _StoryNodeRepo()
    ctx.chapter_repository = _ChapterRepo()

    result = await _Pipeline()._step_find_next_chapter(ctx)

    assert result.passed
    assert ctx.chapter_number == 1
    assert ctx.outline == "新大纲"
    assert ctx.existing_content == ""
    assert ctx.metadata["ignored_existing_draft_chars"] == len("旧半章正文")
