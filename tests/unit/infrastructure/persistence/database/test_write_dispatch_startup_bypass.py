"""启动早期直连 SQLite bypass（与 persistence consumer 次序解耦）。"""

import pytest

from infrastructure.persistence.database import write_dispatch as wd


@pytest.fixture
def clear_direct_write_env(monkeypatch):
    monkeypatch.delenv("AITEXT_ALLOW_DIRECT_SQLITE_WRITES", raising=False)


def test_startup_bypass_enables_allow_direct_writes(clear_direct_write_env):
    assert wd.allow_direct_sqlite_writes() is False

    with wd.startup_sqlite_writes_bypass_queue():
        assert wd.allow_direct_sqlite_writes() is True

    assert wd.allow_direct_sqlite_writes() is False


def test_nested_startup_bypass_restores_depth(clear_direct_write_env):
    with wd.startup_sqlite_writes_bypass_queue():
        with wd.startup_sqlite_writes_bypass_queue():
            assert wd.allow_direct_sqlite_writes() is True
        assert wd.allow_direct_sqlite_writes() is True
    assert wd.allow_direct_sqlite_writes() is False
