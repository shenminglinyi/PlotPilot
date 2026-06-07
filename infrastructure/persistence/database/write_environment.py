"""Environment-backed SQLite write-dispatch configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


PLOTPILOT_DIRECT_SQLITE_WRITES_ENV = "PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES"
LEGACY_DIRECT_SQLITE_WRITES_ENV = "AITEXT_ALLOW_DIRECT_SQLITE_WRITES"


def _env_flag(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class SQLiteWriteEnvironmentSettings:
    """Typed view of SQLite direct-write bypass environment flags."""

    direct_writes: bool = False

    @classmethod
    def from_env(cls) -> "SQLiteWriteEnvironmentSettings":
        raw = os.getenv(PLOTPILOT_DIRECT_SQLITE_WRITES_ENV, "")
        if not (raw or "").strip():
            raw = os.getenv(LEGACY_DIRECT_SQLITE_WRITES_ENV, "")
        return cls(direct_writes=_env_flag(raw))
