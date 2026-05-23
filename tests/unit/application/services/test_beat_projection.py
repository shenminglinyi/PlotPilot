"""Chapter beat projection tests."""
from types import SimpleNamespace

from application.engine.dag.plan.schema import (
    ChapterExecutionPlan,
    PlanAtomSpec,
    PlanningEnvelope,
)
from application.engine.dag.plan.outline_beat_planner import build_chapter_execution_plan_sync
from application.engine.services.beat_projection import (
    OUTLINE_OBLIGATION_PREFIX,
    beat_sheet_to_plan_json,
    beats_from_execution_plan,
    planned_micro_beats_from_beats,
)


def test_beat_sheet_to_plan_json_projects_scene_fields():
    beat_sheet = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                title="夜探库房",
                goal="主角找到账本",
                estimated_words=800,
                pov_character="主角",
                location="库房",
                tone="紧张",
                transition_from_prev="承接上一章线索",
            )
        ]
    )

    payload = beat_sheet_to_plan_json(beat_sheet)

    assert payload == {
        "scenes": [
            {
                "title": "夜探库房",
                "goal": "主角找到账本",
                "estimated_words": 800,
                "pov_character": "主角",
                "location": "库房",
                "tone": "紧张",
                "transition_from_prev": "承接上一章线索",
            }
        ]
    }


def test_execution_plan_projects_to_runtime_beats_with_outline_obligation():
    plan = ChapterExecutionPlan(
        envelope=PlanningEnvelope(target_chapter_words=1000),
        atoms=[
            PlanAtomSpec(
                id="a",
                intent="主角发现账本缺页",
                weight=1,
                extensions={"focus": "suspense", "location_id": "warehouse"},
            ),
            PlanAtomSpec(
                id="b",
                intent="同伴承认早已拿走关键页",
                weight=3,
                extensions={"transition_from_prev": "转入对峙"},
            ),
        ],
        provenance={"mode": "structured_outline"},
    )

    beats = beats_from_execution_plan(
        plan,
        outline="",
        target_chapter_words=1000,
        infer_focus=lambda text: "dialogue",
        build_expansion_hints=lambda focus, words: [f"{focus}:{words}"],
    )

    assert len(beats) == 2
    assert beats[0].description == OUTLINE_OBLIGATION_PREFIX + "主角发现账本缺页"
    assert beats[0].target_words == 250
    assert beats[0].focus == "suspense"
    assert beats[0].location_id == "warehouse"
    assert beats[0].expansion_hints == ["suspense:250"]
    assert beats[1].target_words == 750
    assert beats[1].focus == "dialogue"
    assert beats[1].transition_from_prev == "转入对峙"


def test_planned_micro_beats_from_beats_uses_runtime_serializer():
    beat = SimpleNamespace(
        description="对峙",
        target_words=500,
        focus="dialogue",
        location_id="hall",
        emotion_beat_card=SimpleNamespace(
            active_action="主角把缺页摊在桌上",
            emotion_gap="读者想知道谁背叛",
            forbidden_drift="禁止只写心理活动",
        ),
    )

    payload = planned_micro_beats_from_beats([beat])

    assert payload[0]["description"] == "对峙"
    assert payload[0]["active_action"] == "主角把缺页摊在桌上"
    assert payload[0]["beat_cards"][0]["forbidden_drift"] == "禁止只写心理活动"


def test_sync_plan_builder_makes_beat_sheet_and_outline_canonical_sources():
    beat_sheet_json = {
        "scenes": [
            {"title": "夜探", "goal": "主角找到账本", "estimated_words": 700},
        ]
    }

    from_sheet = build_chapter_execution_plan_sync(
        "章纲正文",
        target_chapter_words=2000,
        beat_sheet_json=beat_sheet_json,
    )
    from_outline = build_chapter_execution_plan_sync(
        "1. 主角潜入库房\n2. 同伴突然背叛",
        target_chapter_words=2000,
    )

    assert from_sheet.provenance["mode"] == "beat_sheet"
    assert from_sheet.atoms[0].intent == "夜探：主角找到账本"
    assert from_outline.provenance["mode"] == "structured_outline"
    assert [a.intent for a in from_outline.atoms] == ["1. 主角潜入库房", "2. 同伴突然背叛"]
