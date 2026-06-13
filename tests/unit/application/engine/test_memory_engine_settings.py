import pytest

from application.core.config.config_loader import reload_config
from application.engine.services.memory_engine_settings import (
    get_memory_engine_runtime_settings,
)


def test_memory_engine_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
memory_engine:
  state_cache_ttl_seconds: 1.25
  state_cache_max_size: 7
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_memory_engine_runtime_settings()

        assert settings.state_cache_ttl_seconds == pytest.approx(1.25)
        assert settings.state_cache_max_size == 7
    finally:
        reload_config()
