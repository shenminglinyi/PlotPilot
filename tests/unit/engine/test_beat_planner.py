"""Rule-based beat planner tests."""

from application.engine.services.beat_planner import (
    generate_expansion_hints,
    infer_focus_from_outline,
    make_minimal_card,
    segment_user_outline,
)


def test_segment_user_outline_numbered_list():
    text = "1. 主角发现密信\n2. 对手逼问真相"

    assert segment_user_outline(text) == ["1. 主角发现密信", "2. 对手逼问真相"]


def test_segment_user_outline_bullets():
    text = "- 茶馆对峙\n- 门外追杀"

    assert segment_user_outline(text) == ["- 茶馆对峙", "- 门外追杀"]


def test_segment_user_outline_sentences():
    text = "主角发现暗格里的密信。对手忽然推门而入。两人开始围绕密信谈判。"

    assert segment_user_outline(text) == [
        "主角发现暗格里的密信。",
        "对手忽然推门而入。",
        "两人开始围绕密信谈判。",
    ]


def test_infer_focus_from_outline_keywords():
    assert infer_focus_from_outline("两人在雨夜战斗") == "action"
    assert infer_focus_from_outline("主角与师父谈判") == "dialogue"
    assert infer_focus_from_outline("她发现真相") == "suspense"
    assert infer_focus_from_outline("他陷入痛苦回忆") == "emotion"
    assert infer_focus_from_outline("街巷灯火渐暗") == "sensory"


def test_generate_expansion_hints_by_target_words():
    hints = {"action": ["a", "b", "c", "d", "e"]}

    assert generate_expansion_hints("action", 1200, hints) == ["a", "b", "c", "d"]
    assert generate_expansion_hints("action", 600, hints) == ["a", "b", "c"]
    assert generate_expansion_hints("action", 300, hints) == ["a", "b"]


def test_make_minimal_card_fields_and_fallback_forbidden_drift():
    card = make_minimal_card("主角发现了藏在暗格里的密信", "suspense", 600)

    assert card.goal == "主角发现了藏在暗格里的密信"
    assert card.function == "suspense"
    assert card.target_words == 600
    assert card.active_action
    assert card.forbidden_drift == "禁止连续两段没有动作、对话、决定之一"
