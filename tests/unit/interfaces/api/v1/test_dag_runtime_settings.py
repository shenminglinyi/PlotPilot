from application.core.config.config_loader import reload_config
from interfaces.api.v1.engine.dag.dag_runtime_settings import get_dag_runtime_settings


def test_dag_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
dag_engine:
  sse:
    queue_size: 7
    idle_poll_seconds: 0.25
    heartbeat_every_idle_ticks: 4
  cache:
    max_size: 9
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_dag_runtime_settings()

        assert settings.sse_queue_size == 7
        assert settings.sse_idle_poll_seconds == 0.25
        assert settings.sse_heartbeat_every_idle_ticks == 4
        assert settings.dag_cache_max_size == 9
    finally:
        reload_config()
