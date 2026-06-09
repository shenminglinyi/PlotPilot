"""SQLite write-path tuning resolved from performance config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.core.config.config_loader import get_config


@dataclass(frozen=True)
class SQLiteWriteSettings:
    micro_transaction_yield_seconds: float = 0.01


def _section_value(section: Any, key: str, default: Any) -> Any:
    if section is None:
        return default
    try:
        value = section.get(key, default)
    except AttributeError:
        return default
    return default if value is None else value


def _as_non_negative_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def get_sqlite_write_settings() -> SQLiteWriteSettings:
    database = getattr(get_config(), "database", None)
    section = getattr(database, "performance", None)
    defaults = SQLiteWriteSettings()
    return SQLiteWriteSettings(
        micro_transaction_yield_seconds=_as_non_negative_float(
            _section_value(
                section,
                "micro_transaction_yield_seconds",
                defaults.micro_transaction_yield_seconds,
            ),
            defaults.micro_transaction_yield_seconds,
        )
    )
