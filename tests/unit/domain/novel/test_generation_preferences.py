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


def test_locked_genre_and_world_preset_roundtrip():
    gp = GenerationPreferences.from_dict(
        {
            "locked_genre": "玄幻 / 东方玄幻",
            "locked_world_preset": "高武末世",
            "locked_story_structure": "废柴开局，逐层升级到宗门争锋。",
            "locked_pacing_control": "三章一兑现，小卷一翻盘，大卷一破阶。",
            "locked_writing_style": "叙事强推进，对话要带压迫感。",
            "locked_special_requirements": "境界、资源、代价必须同步增长。",
        }
    )

    assert gp.locked_genre == "玄幻 / 东方玄幻"
    assert gp.locked_world_preset == "高武末世"
    assert gp.locked_story_structure == "废柴开局，逐层升级到宗门争锋。"
    assert gp.locked_pacing_control == "三章一兑现，小卷一翻盘，大卷一破阶。"
    assert gp.locked_writing_style == "叙事强推进，对话要带压迫感。"
    assert gp.locked_special_requirements == "境界、资源、代价必须同步增长。"

    patched = GenerationPreferences.merge_patch(
        gp,
        {
            "locked_world_preset": "废土修仙",
            "locked_story_structure": "废土求生切入，转向规则争夺与文明重建。",
            "locked_special_requirements": "资源争夺必须可见",
        },
    )
    assert patched.locked_genre == "玄幻 / 东方玄幻"
    assert patched.locked_world_preset == "废土修仙"
    assert patched.locked_story_structure == "废土求生切入，转向规则争夺与文明重建。"
    assert patched.locked_pacing_control == "三章一兑现，小卷一翻盘，大卷一破阶。"
    assert patched.locked_writing_style == "叙事强推进，对话要带压迫感。"
    assert patched.locked_special_requirements == "资源争夺必须可见"
