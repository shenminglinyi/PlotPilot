import pytest

from infrastructure.ai.providers.model_resolution import require_resolved_model_id


def test_resolves_from_config_first():
    assert require_resolved_model_id("  m1  ", "m2", provider_label="P") == "m1"


def test_falls_back_to_settings():
    assert require_resolved_model_id("", "m2", provider_label="P") == "m2"
    assert require_resolved_model_id("  ", " m2 ", provider_label="P") == "m2"


def test_empty_raises():
    with pytest.raises(ValueError, match="未配置模型 ID"):
        require_resolved_model_id("", "", provider_label="Test")
