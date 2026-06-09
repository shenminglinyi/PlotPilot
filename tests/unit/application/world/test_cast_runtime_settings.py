import pytest

from application.core.config.config_loader import reload_config
from application.world.services.cast_runtime_settings import get_cast_runtime_settings


def test_cast_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
world:
  cast:
    runtime:
      graph_cache_ttl_seconds: 0.5
      graph_cache_max_size: 3
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_cast_runtime_settings()

        assert settings.graph_cache_ttl_seconds == pytest.approx(0.5)
        assert settings.graph_cache_max_size == 3
    finally:
        reload_config()
