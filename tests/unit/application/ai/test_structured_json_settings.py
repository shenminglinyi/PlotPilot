import pytest

from application.ai.structured_json_pipeline import _retry_delay_seconds
from application.ai.structured_json_settings import (
    StructuredJSONSettings,
    get_structured_json_settings,
)
from application.core.config.config_loader import reload_config


def test_structured_json_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
ai:
  structured_json:
    retry_backoff_base_seconds: 0.25
    retry_backoff_max_seconds: 0.7
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_structured_json_settings()

        assert settings.retry_backoff_base_seconds == pytest.approx(0.25)
        assert settings.retry_backoff_max_seconds == pytest.approx(0.7)
    finally:
        reload_config()


def test_retry_delay_uses_structured_json_settings():
    settings = StructuredJSONSettings(
        retry_backoff_base_seconds=0.3,
        retry_backoff_max_seconds=1.0,
    )

    assert _retry_delay_seconds(0, settings) == pytest.approx(0.3)
    assert _retry_delay_seconds(2, settings) == pytest.approx(1.0)
