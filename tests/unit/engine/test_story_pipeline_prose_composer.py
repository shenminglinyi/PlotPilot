from __future__ import annotations

import sqlite3

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
async def test_chapter_prose_composer_reuses_committed_story_pipeline_content(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE ai_invocation_sessions (
            id TEXT PRIMARY KEY,
            operation TEXT,
            status TEXT,
            context_json TEXT DEFAULT '{}',
            metadata_json TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE ai_adoption_decisions (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            attempt_id TEXT DEFAULT '',
            accepted_content TEXT DEFAULT '',
            accepted_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE ai_adoption_commits (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            decision_id TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO ai_invocation_sessions
            (id, operation, status, context_json, metadata_json)
        VALUES
            (
                'session-1',
                'autopilot.chapter.prose',
                'completed',
                '{"novel_id":"novel-1","chapter_number":2}',
                '{"commit_owner":"story_pipeline_save_step"}'
            );
        INSERT INTO ai_adoption_decisions
            (id, session_id, accepted_content)
        VALUES ('decision-1', 'session-1', '已采纳正文');
        INSERT INTO ai_adoption_commits
            (id, session_id, decision_id, status)
        VALUES ('commit-1', 'session-1', 'decision-1', 'succeeded');
        """
    )

    class _Db:
        def fetch_one(self, sql, params=()):
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    import infrastructure.persistence.database.connection

    monkeypatch.setattr(infrastructure.persistence.database.connection, "get_database", lambda *_args, **_kwargs: _Db())
    chunks = []
    request = ProseCompositionRequest(
        novel_id="novel-1",
        chapter_number=2,
        stream_sink=chunks.append,
    )

    result = await ChapterProseInvocationComposer().compose(request)

    assert result.content == "已采纳正文"
    assert result.status == "committed_story_pipeline_content"
    assert chunks == ["已采纳正文"]


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
async def test_story_pipeline_save_falls_back_when_queue_write_not_visible(monkeypatch):
    pipeline = _Pipeline()
    ctx = PipelineContext(
        novel_id="novel-save",
        chapter_number=1,
        chapter_content="正文",
        word_count=2,
    )
    ctx.chapter_repository = object()
    saved = []

    async def _save_via_repo(_ctx):
        saved.append((_ctx.novel_id, _ctx.chapter_number, _ctx.chapter_content))

    monkeypatch.setattr(pipeline, "_push_persistence_command", lambda _ctx: True)
    monkeypatch.setattr(pipeline, "_wait_for_chapter_persistence", lambda _ctx: None)
    monkeypatch.setattr(pipeline, "_chapter_completed_in_repository", lambda _ctx: False)
    monkeypatch.setattr(pipeline, "_save_chapter_via_repository", _save_via_repo)

    result = await pipeline._step_save_chapter(ctx)

    assert result.passed
    assert saved == [("novel-save", 1, "正文")]
    assert ctx.chapter_saved is True
    assert ctx.save_method == "queue"


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
