"""V1 体量档推导与黑盒文案"""
from application.core.v1_length_tiers import (
    build_v1_structure_black_box_hint,
    resolve_v1_length_params,
    V1_LENGTH_TIERS,
)


def test_resolve_standard_tier_default_words():
    chapters, wpc, tier = resolve_v1_length_params("standard", 100, None)
    assert tier == "standard"
    assert wpc == 2000
    assert chapters == 500  # 1_000_000 / 2000


def test_resolve_short_tier_custom_words():
    chapters, wpc, tier = resolve_v1_length_params("short", 100, 2400)
    assert tier == "short"
    assert wpc == 2400
    assert chapters == 125  # ceil(300_000 / 2400)


def test_resolve_without_tier_uses_chapters():
    chapters, wpc, tier = resolve_v1_length_params(None, 80, 3000)
    assert tier is None
    assert chapters == 80
    assert wpc == 3000


def test_black_box_contains_volume_hint():
    text = build_v1_structure_black_box_hint("standard", 500, 2000)
    assert "规划目标体量" in text
    assert "勿向读者展示" in text


def test_tier_meta_present():
    assert "approx_total_words" in V1_LENGTH_TIERS["epic"]
