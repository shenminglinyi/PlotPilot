"""Runtime settings shared by persistence queue implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.core.config.config_loader import get_config


@dataclass(frozen=True)
class PersistentQueueSettings:
    batch_size: int = 10
    cleanup_threshold: int = 1000
    cleanup_days: int = 7
    max_retries: int = 3
    zombie_timeout_minutes: int = 5
    queue_bloat_warning: int = 5000
    cleanup_every_processed: int = 100
    consumer_idle_sleep_seconds: float = 0.5
    consumer_error_sleep_seconds: float = 1.0
    consumer_stop_timeout_seconds: float = 5.0
    legacy_lock_max_retries: int = 10
    legacy_lock_backoff_base_seconds: float = 0.2
    legacy_lock_backoff_max_seconds: float = 3.0
    legacy_drain_timeout_seconds: float = 3.0
    legacy_idle_wait_sleep_seconds: float = 0.05
    legacy_idle_stable_checks: int = 3


def _section_value(section: Any, key: str, default: Any) -> Any:
    if section is None:
        return default
    try:
        value = section.get(key, default)
    except AttributeError:
        return default
    return default if value is None else value


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def get_persistent_queue_settings() -> PersistentQueueSettings:
    section = getattr(get_config(), "persistence_queue", None)
    defaults = PersistentQueueSettings()
    return PersistentQueueSettings(
        batch_size=_as_int(_section_value(section, "batch_size", defaults.batch_size), defaults.batch_size),
        cleanup_threshold=_as_int(
            _section_value(section, "cleanup_threshold", defaults.cleanup_threshold),
            defaults.cleanup_threshold,
        ),
        cleanup_days=_as_int(_section_value(section, "cleanup_days", defaults.cleanup_days), defaults.cleanup_days),
        max_retries=_as_int(_section_value(section, "max_retries", defaults.max_retries), defaults.max_retries),
        zombie_timeout_minutes=_as_int(
            _section_value(section, "zombie_timeout_minutes", defaults.zombie_timeout_minutes),
            defaults.zombie_timeout_minutes,
        ),
        queue_bloat_warning=_as_int(
            _section_value(section, "queue_bloat_warning", defaults.queue_bloat_warning),
            defaults.queue_bloat_warning,
        ),
        cleanup_every_processed=_as_int(
            _section_value(section, "cleanup_every_processed", defaults.cleanup_every_processed),
            defaults.cleanup_every_processed,
        ),
        consumer_idle_sleep_seconds=_as_float(
            _section_value(section, "consumer_idle_sleep_seconds", defaults.consumer_idle_sleep_seconds),
            defaults.consumer_idle_sleep_seconds,
        ),
        consumer_error_sleep_seconds=_as_float(
            _section_value(section, "consumer_error_sleep_seconds", defaults.consumer_error_sleep_seconds),
            defaults.consumer_error_sleep_seconds,
        ),
        consumer_stop_timeout_seconds=_as_float(
            _section_value(section, "consumer_stop_timeout_seconds", defaults.consumer_stop_timeout_seconds),
            defaults.consumer_stop_timeout_seconds,
        ),
        legacy_lock_max_retries=_as_int(
            _section_value(section, "legacy_lock_max_retries", defaults.legacy_lock_max_retries),
            defaults.legacy_lock_max_retries,
        ),
        legacy_lock_backoff_base_seconds=_as_float(
            _section_value(
                section,
                "legacy_lock_backoff_base_seconds",
                defaults.legacy_lock_backoff_base_seconds,
            ),
            defaults.legacy_lock_backoff_base_seconds,
        ),
        legacy_lock_backoff_max_seconds=_as_float(
            _section_value(
                section,
                "legacy_lock_backoff_max_seconds",
                defaults.legacy_lock_backoff_max_seconds,
            ),
            defaults.legacy_lock_backoff_max_seconds,
        ),
        legacy_drain_timeout_seconds=_as_float(
            _section_value(section, "legacy_drain_timeout_seconds", defaults.legacy_drain_timeout_seconds),
            defaults.legacy_drain_timeout_seconds,
        ),
        legacy_idle_wait_sleep_seconds=_as_float(
            _section_value(section, "legacy_idle_wait_sleep_seconds", defaults.legacy_idle_wait_sleep_seconds),
            defaults.legacy_idle_wait_sleep_seconds,
        ),
        legacy_idle_stable_checks=_as_int(
            _section_value(section, "legacy_idle_stable_checks", defaults.legacy_idle_stable_checks),
            defaults.legacy_idle_stable_checks,
        ),
    )
