from application.engine.theme.fusion_profile import get_fusion_profile, list_fusion_profiles


def test_fusion_profiles_are_loaded_from_shared_config():
    profile = get_fusion_profile("cyber_xianxia")

    assert profile is not None
    assert profile.label == "赛博剑仙"
    assert profile.primary_theme_key == "xianxia"
    assert profile.character_locks
    assert profile.to_context_text()


def test_list_fusion_profiles_uses_config_loader():
    keys = {profile.key for profile in list_fusion_profiles()}

    assert "cyber_xianxia" in keys
