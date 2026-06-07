"""StoryPipeline 流式正文推送（streaming_bus）单测 — 整章 prose streaming."""
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
async def test_stream_prose_llm_accumulates_full_content():
    pipeline = _Pipeline()
    ctx = PipelineContext(novel_id="novel-stream-1", chapter_number=3, target_word_count=2000)
    ctx.llm_service = MagicMock()
    ctx.llm_service.stream_generate = _mock_stream

    content = await pipeline._stream_prose_llm(ctx, "prompt", MagicMock())

    assert content == "你好，世界"


@pytest.mark.asyncio
async def test_stream_prose_llm_publishes_final_snapshot_to_bus():
    pipeline = _Pipeline()
    # 用 0 间隔确保每次 piece 都会触发 publish；避免依赖时间窗口
    pipeline.STREAM_PUSH_INTERVAL = 0
    ctx = PipelineContext(novel_id="novel-stream-2", chapter_number=1, target_word_count=2000)
    ctx.llm_service = MagicMock()
    ctx.llm_service.stream_generate = _mock_stream

    with patch("application.engine.services.streaming_bus.streaming_bus") as bus:
        content = await pipeline._stream_prose_llm(ctx, "prompt", MagicMock())

    assert content == "你好，世界"
    assert bus.publish.call_count >= 1
    last_call = bus.publish.call_args_list[-1]
    assert last_call.args[0] == "novel-stream-2"
    assert last_call.kwargs.get("content") == "你好，世界"


@pytest.mark.asyncio
async def test_stream_prose_llm_stops_on_stop_signal():
    pipeline = _Pipeline()
    ctx = PipelineContext(novel_id="novel-stream-3", chapter_number=1)
    ctx.llm_service = MagicMock()
    ctx.llm_service.stream_generate = _mock_stream

    with patch.object(_Pipeline, "_novel_stream_should_stop", return_value=True):
        content = await pipeline._stream_prose_llm(ctx, "prompt", MagicMock())

    assert content == ""
