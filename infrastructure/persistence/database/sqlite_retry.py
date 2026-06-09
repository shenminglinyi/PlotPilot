"""SQLite lock retry policy resolved from performance config."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from application.core.config.config_loader import get_config


@dataclass(frozen=True)
class SQLiteRetrySettings:
    lock_max_retries: int = 8
    lock_backoff_base_seconds: float = 0.15
    lock_backoff_max_seconds: float = 2.5
    migration_max_retries: int = 3
    migration_backoff_base_seconds: float = 0.5


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


def get_sqlite_retry_settings() -> SQLiteRetrySettings:
    database = getattr(get_config(), "database", None)
    section = getattr(database, "retry", None)
    defaults = SQLiteRetrySettings()
    return SQLiteRetrySettings(
        lock_max_retries=_as_int(
            _section_value(section, "lock_max_retries", defaults.lock_max_retries),
            defaults.lock_max_retries,
        ),
        lock_backoff_base_seconds=_as_float(
            _section_value(
                section,
                "lock_backoff_base_seconds",
                defaults.lock_backoff_base_seconds,
            ),
            defaults.lock_backoff_base_seconds,
        ),
        lock_backoff_max_seconds=_as_float(
            _section_value(
                section,
                "lock_backoff_max_seconds",
                defaults.lock_backoff_max_seconds,
            ),
            defaults.lock_backoff_max_seconds,
        ),
        migration_max_retries=_as_int(
            _section_value(section, "migration_max_retries", defaults.migration_max_retries),
            defaults.migration_max_retries,
        ),
        migration_backoff_base_seconds=_as_float(
            _section_value(
                section,
                "migration_backoff_base_seconds",
                defaults.migration_backoff_base_seconds,
            ),
            defaults.migration_backoff_base_seconds,
        ),
    )


def is_sqlite_lock_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def lock_retry_delay(attempt: int, settings: SQLiteRetrySettings | None = None) -> float:
    resolved = settings or get_sqlite_retry_settings()
    return min(
        resolved.lock_backoff_base_seconds * (2**attempt),
        resolved.lock_backoff_max_seconds,
    )


def migration_retry_delay(attempt: int, settings: SQLiteRetrySettings | None = None) -> float:
    resolved = settings or get_sqlite_retry_settings()
    return resolved.migration_backoff_base_seconds * (attempt + 1)
