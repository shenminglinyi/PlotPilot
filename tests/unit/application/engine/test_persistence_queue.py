import sqlite3

import pytest

from application.core.config.config_loader import reload_config
from application.engine.services.persistence_queue import PersistenceQueue


def test_legacy_persistence_queue_uses_configured_lock_backoff(tmp_path, monkeypatch):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
persistence_queue:
  legacy_lock_max_retries: 3
  legacy_lock_backoff_base_seconds: 0.1
  legacy_lock_backoff_max_seconds: 0.15
""",
        encoding="utf-8",
    )

    sleeps = []
    attempts = {"count": 0}

    def sleep(seconds):
        sleeps.append(seconds)

    def handler(_payload):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise sqlite3.OperationalError("database is locked")

    try:
        reload_config(str(config_path))
        monkeypatch.setattr("application.engine.services.persistence_queue.time.sleep", sleep)

        queue = PersistenceQueue()
        queue.register_handler("cmd", handler)
        queue._process_single_command("cmd", {})

        assert attempts["count"] == 3
        assert sleeps == pytest.approx([0.1, 0.15])
    finally:
        reload_config()
