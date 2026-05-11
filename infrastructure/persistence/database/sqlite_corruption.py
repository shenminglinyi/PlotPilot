"""Classify SQLite failures: on-disk corruption vs transient errors (lock/busy, etc.)."""
from __future__ import annotations

import sqlite3

# OperationalError messages that should not be treated as file corruption.
_TRANSIENT_OPERATIONAL_HINTS = (
    "locked",
    "busy",
)

# Substrings from SQLite when the db file is damaged or not a valid database.
_CORRUPTION_HINTS = (
    "malformed",
    "disk image",
    "file is not a database",
)


def is_sqlite_storage_corruption(exc: BaseException) -> bool:
    """Return True if *exc* indicates persistent storage corruption, not a transient lock.

    Note: :class:`sqlite3.OperationalError` subclasses :class:`sqlite3.DatabaseError`;
    we only flag corruption when the message matches known patterns and is not lock/busy.
    """
    if not isinstance(exc, sqlite3.DatabaseError):
        return False
    msg = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError):
        if any(hint in msg for hint in _TRANSIENT_OPERATIONAL_HINTS):
            return False
    return any(hint in msg for hint in _CORRUPTION_HINTS)
