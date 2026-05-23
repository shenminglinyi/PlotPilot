from types import SimpleNamespace

import pytest

from application.engine.dag.models import NodeStatus
from application.engine.dag.nodes import execution_nodes
from application.engine.dag.nodes.execution_nodes import BeatNode
from application.engine.dag.plan.schema import ChapterExecutionPlan


@pytest.mark.asyncio
async def test_exec_beat_sync_fallback_still_passes_chapter_execution_plan(monkeypatch):
    captured = {}

    async def fail_async_plan(*args, **kwargs):
        raise RuntimeError("planner unavailable")

    class FakeBuilder:
        def magnify_outline_to_beats(self, chapter_number, outline, **kwargs):
            captured["chapter_number"] = chapter_number
            captured["outline"] = outline
            captured["kwargs"] = kwargs
            assert isinstance(kwargs["chapter_execution_plan"], ChapterExecutionPlan)
            assert kwargs["beat_sheet"] is None
            return [
                SimpleNamespace(
                    description="主角在雨夜发现账本",
                    target_words=800,
                    focus="suspense",
                    location_id="warehouse",
                    emotion_beat_card=SimpleNamespace(
                        active_action="主角把账本藏进衣内",
                        emotion_gap="读者想知道账本缺页去了哪里",
                        forbidden_drift="禁止只写氛围",
                    ),
                )
            ]

    monkeypatch.setattr(execution_nodes, "_dag_context_builder", lambda: FakeBuilder())
    monkeypatch.setattr(
        "application.engine.dag.plan.outline_beat_planner.build_chapter_execution_plan_async",
        fail_async_plan,
    )

    result = await BeatNode().execute(
        {
            "outline": "主角夜探库房，发现账本缺页",
            "target_chapter_words": 1600,
            "beat_sheet_json": {
                "scenes": [
                    {"title": "夜探", "goal": "发现账本缺页", "estimated_words": 700},
                ]
            },
        },
        {"novel_id": "n1", "chapter_number": 3},
    )

    assert result.status == NodeStatus.SUCCESS
    assert captured["chapter_number"] == 3
    assert captured["kwargs"]["chapter_execution_plan"].provenance["mode"] == "beat_sheet"
    assert result.outputs["beats"][0]["description"] == "主角在雨夜发现账本"
    assert result.outputs["beats"][0]["beat_cards"][0]["forbidden_drift"] == "禁止只写氛围"


@pytest.mark.asyncio
async def test_exec_beat_without_context_builder_does_not_create_runtime_beat_from_outline(monkeypatch):
    monkeypatch.setattr(execution_nodes, "_dag_context_builder", lambda: None)

    result = await BeatNode().execute(
        {"outline": "主角夜探库房", "target_chapter_words": 1200},
        {"novel_id": "n1", "chapter_number": 1},
    )

    assert result.status == NodeStatus.SUCCESS
    assert result.outputs["beats"] == []
