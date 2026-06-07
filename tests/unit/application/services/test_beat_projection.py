"""Chapter beat projection tests."""
from types import SimpleNamespace

from application.engine.dag.plan.schema import (
    ChapterExecutionPlan,
    PlanAtomSpec,
    PlanDecompositionMode,
    PlanningEnvelope,
)
from application.engine.dag.plan.outline_beat_planner import build_chapter_execution_plan_sync
from application.engine.services.beat_projection import (
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


def test_execution_plan_projects_to_runtime_beats_without_prompt_obligation_prefix():
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
    assert beats[0].description == "主角发现账本缺页"
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


def test_planned_micro_beats_from_beats_preserves_dict_runtime_shape():
    payload = planned_micro_beats_from_beats(
        [
            {
                "description": "转入追逐",
                "target_words": 450,
                "focus": "action",
                "location_id": "alley",
                "beat_cards": [
                    {
                        "active_action": "主角撞开后门",
                        "emotion_gap": "读者担心追兵逼近",
                        "forbidden_drift": "禁止停下来解释设定",
                    }
                ],
            }
        ]
    )

    assert payload[0]["description"] == "转入追逐"
    assert payload[0]["focus"] == "action"
    assert payload[0]["beat_cards"][0]["active_action"] == "主角撞开后门"


def test_default_contract_fields_use_short_summary_not_full_intent():
    long_intent = (
        "司徒寒在南州城贫民窟暗巷中遭遇前世仇敌——黑鲨帮余孽三人组。"
        "利用重生记忆，他精准预判对方刀路，反手夺刀割喉。"
    )
    plan = ChapterExecutionPlan(
        envelope=PlanningEnvelope(target_chapter_words=2000),
        atoms=[PlanAtomSpec(id="b1", intent=long_intent, weight=1.0)],
        provenance={"mode": PlanDecompositionMode.RAW_OUTLINE_SINGLE.value},
    )
    beats = beats_from_execution_plan(
        plan,
        outline="",
        target_chapter_words=2000,
        infer_focus=lambda text: "sensory",
        build_expansion_hints=lambda focus, words: [],
    )
    assert len(beats) == 1
    assert beats[0].visible_action == "用可见动作、对白或选择落实：司徒寒在南州城贫民窟暗巷中遭遇前世仇敌——黑鲨帮余孽三人组。"
    assert long_intent not in beats[0].delta
    assert "司徒寒" in beats[0].delta


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
    from_single_outline = build_chapter_execution_plan_sync(
        "主角在一整段章纲里完成调查并被迫做出选择",
        target_chapter_words=2000,
    )

    assert from_sheet.provenance["mode"] == PlanDecompositionMode.BEAT_SHEET.value
    assert from_sheet.atoms[0].intent == "夜探：主角找到账本"
    assert from_outline.provenance["mode"] == PlanDecompositionMode.STRUCTURED_OUTLINE.value
    assert [a.intent for a in from_outline.atoms] == ["1. 主角潜入库房", "2. 同伴突然背叛"]
    assert from_single_outline.provenance["mode"] == PlanDecompositionMode.RAW_OUTLINE_SINGLE.value
    assert from_single_outline.atoms[0].extensions["decomposition_mode"] == PlanDecompositionMode.RAW_OUTLINE_SINGLE.value
