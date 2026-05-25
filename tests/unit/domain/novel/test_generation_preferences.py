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


def test_audit_gate_prefs_default_false_when_missing():
    gp = GenerationPreferences.from_dict({"phase_display_mode": True})
    assert gp.pause_after_each_chapter_audit is False
    assert gp.audit_pause_on_hard_fail is False
    assert gp.audit_pause_on_anti_ai_severe is False


def test_beat_safety_net_defaults_off():
    gp = GenerationPreferences()
    assert gp.beat_hard_cap_enabled is False
    assert gp.smart_truncate_enabled is False

    partial = GenerationPreferences.from_dict({"phase_display_mode": True})
    assert partial.beat_hard_cap_enabled is False
    assert partial.smart_truncate_enabled is False


def test_audit_gate_prefs_from_dict_merge_patch():
    gp = GenerationPreferences.from_dict(
        {
            "pause_after_each_chapter_audit": True,
            "audit_pause_on_hard_fail": True,
            "audit_pause_on_anti_ai_severe": True,
        }
    )
    assert gp.pause_after_each_chapter_audit is True
    assert gp.audit_pause_on_hard_fail is True
    assert gp.audit_pause_on_anti_ai_severe is True

    patched = GenerationPreferences.merge_patch(gp, {"pause_after_each_chapter_audit": False})
    assert patched.pause_after_each_chapter_audit is False
    assert patched.audit_pause_on_hard_fail is True
