import sqlite3

import pytest

from application.core.config.config_loader import reload_config
from infrastructure.persistence.database.connection_pool import SQLiteConnectionPool
from infrastructure.persistence.database.sqlite_pragmas import (
    apply_standard_pragmas,
    get_sqlite_pragma_settings,
)
from infrastructure.persistence.database.sqlite_retry import (
    get_sqlite_retry_settings,
    lock_retry_delay,
    migration_retry_delay,
)
from infrastructure.persistence.database.sqlite_write_settings import get_sqlite_write_settings


def test_sqlite_pragma_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
database:
  connection_pool:
    busy_timeout: 1234
  wal:
    auto_checkpoint: 77
  performance:
    synchronous: NORMAL
    temp_store: MEMORY
    mmap_size: 4096
    cache_size: -512
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))

        settings = get_sqlite_pragma_settings()

        assert settings.busy_timeout_ms == 1234
        assert settings.wal_autocheckpoint == 77
        assert settings.synchronous == "NORMAL"
        assert settings.temp_store == "MEMORY"
        assert settings.mmap_size == 4096
        assert settings.cache_size == -512
    finally:
        reload_config()


def test_apply_standard_pragmas_uses_resolved_settings(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
database:
  connection_pool:
    busy_timeout: 2345
  wal:
    auto_checkpoint: 88
""",
        encoding="utf-8",
    )

    db_path = tmp_path / "pragma.db"
    try:
        reload_config(str(config_path))
        conn = sqlite3.connect(db_path)
        try:
            apply_standard_pragmas(conn)

            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 2345
            assert conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 88
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()
    finally:
        reload_config()


def test_connection_pool_size_uses_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
database:
  connection_pool:
    size: 3
    busy_timeout: 1000
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        pool = SQLiteConnectionPool(str(tmp_path / "pool.db"))
        try:
            assert pool.pool_size == 3
            pool.initialize()
            assert pool.get_stats()["available_connections"] == 3
        finally:
            pool.close_all()
    finally:
        reload_config()


def test_sqlite_retry_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
database:
  retry:
    lock_max_retries: 4
    lock_backoff_base_seconds: 0.2
    lock_backoff_max_seconds: 0.7
    migration_max_retries: 5
    migration_backoff_base_seconds: 0.3
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_sqlite_retry_settings()

        assert settings.lock_max_retries == 4
        assert settings.lock_backoff_base_seconds == 0.2
        assert settings.lock_backoff_max_seconds == 0.7
        assert settings.migration_max_retries == 5
        assert settings.migration_backoff_base_seconds == 0.3
        assert lock_retry_delay(3, settings) == 0.7
        assert migration_retry_delay(2, settings) == pytest.approx(0.9)
    finally:
        reload_config()


def test_sqlite_write_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
database:
  performance:
    micro_transaction_yield_seconds: 0.025
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_sqlite_write_settings()

        assert settings.micro_transaction_yield_seconds == pytest.approx(0.025)
    finally:
        reload_config()
