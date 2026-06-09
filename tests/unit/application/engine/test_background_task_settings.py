import pytest

from application.core.config.config_loader import reload_config
from application.engine.services.background_task_service import BackgroundTaskService
from application.engine.services.background_task_settings import (
    BackgroundTaskSettings,
    background_task_retry_delay,
    get_background_task_settings,
)


def test_background_task_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
background_tasks:
  worker_count: 4
  queue_max_size: 25
  queue_get_timeout_seconds: 0.4
  worker_join_timeout_seconds: 0.3
  task_max_retries: 0
  retry_backoff_base_seconds: 0.2
  retry_backoff_max_seconds: 0.5
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_background_task_settings()

        assert settings.worker_count == 4
        assert settings.queue_max_size == 25
        assert settings.queue_get_timeout_seconds == pytest.approx(0.4)
        assert settings.worker_join_timeout_seconds == pytest.approx(0.3)
        assert settings.task_max_retries == 0
        assert settings.retry_backoff_base_seconds == pytest.approx(0.2)
        assert settings.retry_backoff_max_seconds == pytest.approx(0.5)
    finally:
        reload_config()


def test_background_task_retry_delay_is_capped():
    settings = BackgroundTaskSettings(
        retry_backoff_base_seconds=0.25,
        retry_backoff_max_seconds=0.6,
    )

    assert background_task_retry_delay(0, settings) == pytest.approx(0.25)
    assert background_task_retry_delay(2, settings) == pytest.approx(0.6)


def test_background_task_service_shutdown_stops_workers(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
background_tasks:
  worker_count: 1
  queue_max_size: 4
  queue_get_timeout_seconds: 0.05
  worker_join_timeout_seconds: 0.5
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        service = BackgroundTaskService()
        service.shutdown()

        assert all(not worker.is_alive() for worker in service._workers)
    finally:
        reload_config()
