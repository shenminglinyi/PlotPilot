"""StoryPipeline 流式正文推送（streaming_bus）单测."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext


class _Pipeline(BaseStoryPipeline):
    pass


async def _mock_stream(*_args, **_kwargs):
    for piece in ("你好", "，", "世界"):
        yield piece


@pytest.mark.asyncio
async def test_stream_beat_llm_publishes_snapshots():
    pipeline = _Pipeline()
    ctx = PipelineContext(novel_id="novel-stream-1", chapter_number=3, target_word_count=2000)
    ctx.llm_service = MagicMock()
    ctx.llm_service.stream_generate = _mock_stream

    with patch("application.engine.services.streaming_bus.streaming_bus") as bus:
        content = await pipeline._stream_beat_llm(
            ctx,
            "prompt",
            MagicMock(),
            chapter_draft_so_far="",
            beat_index=0,
            n_beats=2,
        )

    assert content == "你好，世界"
    assert bus.publish.call_count >= 1
    last_call = bus.publish.call_args_list[-1]
    assert last_call.kwargs.get("content") == "你好，世界"
    assert last_call.args[0] == "novel-stream-1"


@pytest.mark.asyncio
async def test_stream_beat_llm_includes_prior_beats_in_snapshot():
    pipeline = _Pipeline()
    ctx = PipelineContext(novel_id="novel-stream-2", chapter_number=1)
    ctx.llm_service = MagicMock()
    ctx.llm_service.stream_generate = _mock_stream

    with patch("application.engine.services.streaming_bus.streaming_bus") as bus:
        await pipeline._stream_beat_llm(
            ctx,
            "prompt",
            MagicMock(),
            chapter_draft_so_far="上一节拍",
            beat_index=1,
            n_beats=2,
        )

    snapshots = [c.kwargs.get("content") for c in bus.publish.call_args_list if c.kwargs.get("content")]
    assert any(s and s.startswith("上一节拍") and "你好" in s for s in snapshots)
