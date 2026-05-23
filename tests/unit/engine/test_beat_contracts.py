"""StoryPipeline beat contract helper tests."""
from types import SimpleNamespace

from engine.pipeline.beat_contracts import merge_beats_by_target


def _beat(description: str, card_block: str, target_words: int = 600):
    return SimpleNamespace(
        description=description,
        target_words=target_words,
        focus="action",
        scene_goal=description,
        transition_from_prev="",
        location_id="",
        card_prompt_block=card_block,
        emotion_beat_card=SimpleNamespace(
            active_action=f"行动-{description}",
            emotion_gap=f"缺口-{description}",
            forbidden_drift=f"禁止-{description}",
        ),
    )


def test_merge_beats_preserves_all_card_blocks_for_short_chapter():
    beats = [
        _beat("一", "active_action=A\nemotion_gap=EA\nforbidden_drift=FA"),
        _beat("二", "active_action=B\nemotion_gap=EB\nforbidden_drift=FB"),
        _beat("三", "active_action=C\nemotion_gap=EC\nforbidden_drift=FC"),
    ]

    merged = merge_beats_by_target(beats, total_target=2000)

    assert len(merged) == 1
    block = merged[0].card_prompt_block
    for expected in ("active_action=A", "active_action=B", "active_action=C"):
        assert expected in block
    for expected in ("emotion_gap=EA", "emotion_gap=EB", "emotion_gap=EC"):
        assert expected in block
    for expected in ("forbidden_drift=FA", "forbidden_drift=FB", "forbidden_drift=FC"):
        assert expected in block


def test_merge_beats_keeps_pipeline_compatible_shape():
    merged = merge_beats_by_target([_beat("一", "card A", 300), _beat("二", "card B", 300)], 5000)

    assert len(merged) == 1
    assert merged[0].description
    assert merged[0].target_words == 600
    assert merged[0].focus == "action"
    assert "card A" in merged[0].card_prompt_block
    assert "card B" in merged[0].card_prompt_block
