import pytest

from application.core.config.config_loader import reload_config
from interfaces.api.v1.world.bible_runtime_settings import get_bible_runtime_settings


def test_bible_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
bible:
  runtime:
    worldbuilding_field_emit_delay_seconds: 0
    worldbuilding_dimension_emit_delay_seconds: 0.07
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_bible_runtime_settings()

        assert settings.worldbuilding_field_emit_delay_seconds == 0
        assert settings.worldbuilding_dimension_emit_delay_seconds == pytest.approx(0.07)
    finally:
        reload_config()
