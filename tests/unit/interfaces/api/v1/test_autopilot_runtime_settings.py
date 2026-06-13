import pytest

from application.core.config.config_loader import reload_config
from interfaces.api.v1.engine.autopilot_runtime_settings import (
    get_autopilot_runtime_settings,
)


def test_autopilot_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
autopilot:
  runtime:
    sse_thread_pool_workers: 6
    shared_state_cache_ttl_seconds: 0.5
    shared_state_cache_max_size: 128
    sse_max_lifetime_seconds: 60
    db_read_timeout_seconds: 1.5
    db_persist_timeout_seconds: 9
    persistence_idle_timeout_seconds: 4
    persistence_fallback_idle_timeout_seconds: 2
    sse_tick_timeout_seconds: 0.75
    sse_missing_check_timeout_seconds: 0.25
    log_poll_seconds: 1.25
    log_missing_keepalive_seconds: 2.5
    log_heartbeat_every_ticks: 3
    log_stream_max_events: 77
    chapter_active_poll_seconds: 0.4
    chapter_slow_poll_seconds: 4
    chapter_heartbeat_every_ticks: 5
    chapter_empty_status_check_polls: 6
    chapter_stream_max_chunks: 9
    events_poll_seconds: 1.75
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_autopilot_runtime_settings()

        assert settings.sse_thread_pool_workers == 6
        assert settings.shared_state_cache_ttl_seconds == 0.5
        assert settings.shared_state_cache_max_size == 128
        assert settings.sse_max_lifetime_seconds == 60
        assert settings.db_read_timeout_seconds == 1.5
        assert settings.db_persist_timeout_seconds == 9
        assert settings.persistence_idle_timeout_seconds == 4
        assert settings.persistence_fallback_idle_timeout_seconds == 2
        assert settings.sse_tick_timeout_seconds == 0.75
        assert settings.sse_missing_check_timeout_seconds == 0.25
        assert settings.log_poll_seconds == 1.25
        assert settings.log_missing_keepalive_seconds == 2.5
        assert settings.log_heartbeat_every_ticks == 3
        assert settings.log_stream_max_events == 77
        assert settings.chapter_active_poll_seconds == pytest.approx(0.4)
        assert settings.chapter_slow_poll_seconds == 4
        assert settings.chapter_heartbeat_every_ticks == 5
        assert settings.chapter_empty_status_check_polls == 6
        assert settings.chapter_stream_max_chunks == 9
        assert settings.events_poll_seconds == 1.75
    finally:
        reload_config()
