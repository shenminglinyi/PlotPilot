import sqlite3
from unittest.mock import MagicMock

import pytest

from infrastructure.persistence.database.sqlite_corruption import is_sqlite_storage_corruption
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository


def test_malformed_database_error_is_corruption():
    exc = sqlite3.DatabaseError("database disk image is malformed")
    assert is_sqlite_storage_corruption(exc) is True


def test_operational_locked_is_not_corruption():
    exc = sqlite3.OperationalError("database is locked")
    assert is_sqlite_storage_corruption(exc) is False


def test_operational_table_locked_is_not_corruption():
    exc = sqlite3.OperationalError("database table is locked")
    assert is_sqlite_storage_corruption(exc) is False


def test_operational_busy_is_not_corruption():
    exc = sqlite3.OperationalError("database is busy")
    assert is_sqlite_storage_corruption(exc) is False


@pytest.mark.parametrize(
    "cls, msg",
    [
        (sqlite3.DatabaseError, "file is not a database"),
        (sqlite3.OperationalError, "database disk image is malformed"),
    ],
)
def test_corruption_patterns(cls, msg):
    assert is_sqlite_storage_corruption(cls(msg)) is True


def test_novel_repo_list_all_empty_on_corruption():
    db = MagicMock()
    db.fetch_all.side_effect = sqlite3.DatabaseError("database disk image is malformed")
    repo = SqliteNovelRepository(db)
    assert repo.list_all() == []
    assert repo.consume_sqlite_corruption_warning() is not None


def test_novel_repo_list_all_propagates_lock():
    db = MagicMock()
    db.fetch_all.side_effect = sqlite3.OperationalError("database is locked")
    repo = SqliteNovelRepository(db)
    with pytest.raises(sqlite3.OperationalError):
        repo.list_all()
    assert repo.consume_sqlite_corruption_warning() is None
