from types import SimpleNamespace

from application.engine.services.context_lifecycle import (
    DEFAULT_PHASE_THRESHOLDS,
    build_lifecycle_directive,
    classify_phase,
    estimate_total_chapters,
    get_phase_directives,
    load_phase_thresholds,
)
from engine.core.entities.story import StoryPhase


class FakeRegistry:
    def __init__(self, fields=None, directives=None):
        self.fields = fields or {}
        self.directives = directives or {}

    def get_field(self, _prompt_id, key, default=None):
        return self.fields.get(key, default)

    def get_directives_dict(self, _prompt_id, directives_key="_directives"):
        return self.directives


class FakeStoryNodeRepository:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_by_novel_sync(self, _novel_id):
        return self.nodes


def _node(node_type, *, chapter_end=None, suggested_chapter_count=None, number=None):
    return SimpleNamespace(
        node_type=SimpleNamespace(value=node_type),
        chapter_end=chapter_end,
        suggested_chapter_count=suggested_chapter_count,
        number=number,
    )


def test_estimate_total_chapters_prefers_part_end_then_suggested_count():
    assert estimate_total_chapters(
        FakeStoryNodeRepository([_node("part", chapter_end=80)]),
        "novel-1",
    ) == 80

    assert estimate_total_chapters(
        FakeStoryNodeRepository(
            [
                _node("part", suggested_chapter_count=30),
                _node("part", suggested_chapter_count=40),
            ]
        ),
        "novel-1",
    ) == 70


def test_estimate_total_chapters_falls_back_from_chapter_nodes():
    total = estimate_total_chapters(
        FakeStoryNodeRepository([_node("chapter", number=50)]),
        "novel-1",
    )

    assert total == 60


def test_phase_thresholds_and_classification_are_configurable():
    thresholds = load_phase_thresholds(
        FakeRegistry(fields={"_phase_thresholds": {"opening": 0.2, "convergence": 0.8}}),
        "prompt",
        DEFAULT_PHASE_THRESHOLDS,
    )

    assert thresholds["opening"] == 0.2
    assert thresholds["convergence"] == 0.8
    assert classify_phase(0.1, thresholds) == StoryPhase.OPENING
    assert classify_phase(0.2, thresholds) == StoryPhase.DEVELOPMENT
    assert classify_phase(0.81, thresholds) == StoryPhase.CONVERGENCE


def test_build_lifecycle_directive_renders_directive_and_extra():
    directive = build_lifecycle_directive(
        story_node_repository=FakeStoryNodeRepository([_node("part", chapter_end=100)]),
        novel_id="novel-1",
        chapter_number=92,
        thresholds=DEFAULT_PHASE_THRESHOLDS,
        registry=FakeRegistry(
            fields={"_convergence_extra": "还剩 {remaining} 章，收束所有承诺。\n"},
            directives={"CONVERGENCE": "开始汇流"},
        ),
        prompt_id="prompt",
    )

    assert "开始汇流" in directive
    assert "第 92 章 / 约 100 章" in directive
    assert "还剩 8 章" in directive


def test_get_phase_directives_ignores_unknown_keys():
    directives = get_phase_directives(
        FakeRegistry(directives={"OPENING": "开局", "UNKNOWN": "nope"}),
        "prompt",
    )

    assert directives == {StoryPhase.OPENING: "开局"}
