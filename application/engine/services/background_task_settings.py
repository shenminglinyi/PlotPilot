"""Runtime tuning for background task workers."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    non_negative_int,
    positive_float,
    positive_int,
    section_value,
)


@dataclass(frozen=True)
class BackgroundTaskSettings:
    worker_count: int = 3
    queue_max_size: int = 200
    queue_get_timeout_seconds: float = 2.0
    worker_join_timeout_seconds: float = 2.0
    task_max_retries: int = 2
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_max_seconds: float = 8.0


def get_background_task_settings() -> BackgroundTaskSettings:
    section = getattr(get_config(), "background_tasks", None)
    defaults = BackgroundTaskSettings()
    return BackgroundTaskSettings(
        worker_count=positive_int(
            section_value(section, "worker_count", defaults.worker_count),
            defaults.worker_count,
        ),
        queue_max_size=positive_int(
            section_value(section, "queue_max_size", defaults.queue_max_size),
            defaults.queue_max_size,
        ),
        queue_get_timeout_seconds=positive_float(
            section_value(
                section,
                "queue_get_timeout_seconds",
                defaults.queue_get_timeout_seconds,
            ),
            defaults.queue_get_timeout_seconds,
        ),
        worker_join_timeout_seconds=positive_float(
            section_value(
                section,
                "worker_join_timeout_seconds",
                defaults.worker_join_timeout_seconds,
            ),
            defaults.worker_join_timeout_seconds,
        ),
        task_max_retries=non_negative_int(
            section_value(section, "task_max_retries", defaults.task_max_retries),
            defaults.task_max_retries,
        ),
        retry_backoff_base_seconds=positive_float(
            section_value(
                section,
                "retry_backoff_base_seconds",
                defaults.retry_backoff_base_seconds,
            ),
            defaults.retry_backoff_base_seconds,
        ),
        retry_backoff_max_seconds=positive_float(
            section_value(
                section,
                "retry_backoff_max_seconds",
                defaults.retry_backoff_max_seconds,
            ),
            defaults.retry_backoff_max_seconds,
        ),
    )


def background_task_retry_delay(attempt: int, settings: BackgroundTaskSettings | None = None) -> float:
    resolved = settings or get_background_task_settings()
    return min(
        resolved.retry_backoff_base_seconds * (2**attempt),
        resolved.retry_backoff_max_seconds,
    )
