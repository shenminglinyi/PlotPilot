"""Shared SQLite PRAGMA setup for every connection entry point."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from application.core.config.config_loader import get_config


@dataclass(frozen=True)
class SQLitePragmaSettings:
    busy_timeout_ms: int = 30000
    wal_autocheckpoint: int = 1000
    synchronous: str = "NORMAL"
    temp_store: str = "MEMORY"
    mmap_size: int = 268435456
    cache_size: int = -32768


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
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_sqlite_keyword(value: Any, default: str) -> str:
    raw = str(value or default).strip().upper()
    return raw if raw.replace("_", "").isalnum() else default


def get_sqlite_pragma_settings() -> SQLitePragmaSettings:
    """Resolve SQLite PRAGMA settings from config/performance.yaml with safe defaults."""
    cfg = get_config()
    database = getattr(cfg, "database", None)
    pool_cfg = getattr(database, "connection_pool", None)
    wal_cfg = getattr(database, "wal", None)
    perf_cfg = getattr(database, "performance", None)

    return SQLitePragmaSettings(
        busy_timeout_ms=_as_int(
            _section_value(pool_cfg, "busy_timeout", SQLitePragmaSettings.busy_timeout_ms),
            SQLitePragmaSettings.busy_timeout_ms,
        ),
        wal_autocheckpoint=_as_int(
            _section_value(wal_cfg, "auto_checkpoint", SQLitePragmaSettings.wal_autocheckpoint),
            SQLitePragmaSettings.wal_autocheckpoint,
        ),
        synchronous=_as_sqlite_keyword(
            _section_value(perf_cfg, "synchronous", SQLitePragmaSettings.synchronous),
            SQLitePragmaSettings.synchronous,
        ),
        temp_store=_as_sqlite_keyword(
            _section_value(perf_cfg, "temp_store", SQLitePragmaSettings.temp_store),
            SQLitePragmaSettings.temp_store,
        ),
        mmap_size=_as_int(
            _section_value(perf_cfg, "mmap_size", SQLitePragmaSettings.mmap_size),
            SQLitePragmaSettings.mmap_size,
        ),
        cache_size=_as_int(
            _section_value(perf_cfg, "cache_size", SQLitePragmaSettings.cache_size),
            SQLitePragmaSettings.cache_size,
        ),
    )


# Compatibility for older imports; runtime values are resolved from configuration.
BUSY_TIMEOUT_MS = get_sqlite_pragma_settings().busy_timeout_ms


def apply_standard_pragmas(conn: sqlite3.Connection) -> None:
    """Apply standard PRAGMAs immediately after sqlite3.connect."""
    settings = get_sqlite_pragma_settings()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={settings.busy_timeout_ms}")
    conn.execute(f"PRAGMA wal_autocheckpoint={settings.wal_autocheckpoint}")
    conn.execute(f"PRAGMA synchronous={settings.synchronous}")
    conn.execute(f"PRAGMA temp_store={settings.temp_store}")
    conn.execute(f"PRAGMA mmap_size={settings.mmap_size}")
    conn.execute(f"PRAGMA cache_size={settings.cache_size}")
