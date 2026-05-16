"""GenerationPreferences：from_dict / merge_patch 兼容性。"""
from domain.novel.value_objects.generation_preferences import GenerationPreferences


def test_missing_inline_prose_aggregation_defaults_false():
    gp = GenerationPreferences.from_dict({"phase_display_mode": True})
    assert gp.inline_prose_aggregation_enabled is False


def test_explicit_inline_prose_aggregation_true():
    gp = GenerationPreferences.from_dict({"inline_prose_aggregation_enabled": True})
    assert gp.inline_prose_aggregation_enabled is True


def test_merge_patch_roundtrip_key():
    base = GenerationPreferences()
    patched = GenerationPreferences.merge_patch(
        base, {"inline_prose_aggregation_enabled": True}
    )
    assert patched.inline_prose_aggregation_enabled is True
    assert "inline_prose_aggregation_enabled" in patched.to_dict()
