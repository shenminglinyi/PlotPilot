import pytest

from application.analyst.services.voice_analysis_settings import (
    get_voice_analysis_runtime_settings,
)
from application.core.config.config_loader import reload_config


def test_voice_analysis_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
analyst:
  voice_analysis:
    style_cache_ttl_seconds: 1.5
    style_cache_max_size: 11
    baseline_cache_ttl_seconds: 2.5
    baseline_cache_max_size: 7
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_voice_analysis_runtime_settings()

        assert settings.style_cache_ttl_seconds == pytest.approx(1.5)
        assert settings.style_cache_max_size == 11
        assert settings.baseline_cache_ttl_seconds == pytest.approx(2.5)
        assert settings.baseline_cache_max_size == 7
    finally:
        reload_config()
