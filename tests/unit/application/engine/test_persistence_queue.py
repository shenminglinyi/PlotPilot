import sqlite3
import threading

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


def test_writer_skips_expired_request_and_reports_execution_error():
    queue = PersistenceQueue()
    channel = queue.initialize()
    entered, release = threading.Event(), threading.Event()
    observed = []

    def hold(_):
        entered.set()
        assert release.wait(5)

    def fail(_):
        raise sqlite3.IntegrityError("rejected")

    queue.register_handler("hold", hold)
    queue.register_handler("record", lambda payload: observed.append(payload))
    queue.register_handler("fail", fail)
    queue.start_consumer()
    try:
        assert queue.push("hold", {})
        assert entered.wait(5)
        with pytest.raises(TimeoutError):
            queue.submit_and_wait("record", {"run": 1}, timeout=0.01)
        release.set()
        with pytest.raises(sqlite3.IntegrityError, match="rejected"):
            queue.submit_and_wait("fail", {}, timeout=3)
        assert observed == []
    finally:
        release.set()
        queue.stop_consumer()
        channel.close()
        channel.join_thread()
