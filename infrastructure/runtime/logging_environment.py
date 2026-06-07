"""Environment-backed logging presentation and rotation settings."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


@dataclass(frozen=True)
class LoggingEnvironmentSettings:
    """Typed view of logging-related environment variables."""

    debug_http: bool = False
    color_mode: str = "auto"
    no_color: bool = False
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5

    @classmethod
    def from_env(cls) -> "LoggingEnvironmentSettings":
        return cls(
            debug_http=_truthy(os.getenv("DEBUG_HTTP", "")),
            color_mode=(os.getenv("LOG_COLOR", "auto") or "auto").strip().lower(),
            no_color=bool(os.getenv("NO_COLOR")),
            max_bytes=_env_int("LOG_MAX_BYTES", 10 * 1024 * 1024),
            backup_count=_env_int("LOG_BACKUP_COUNT", 5),
        )

    def should_use_color(self, stream: Any | None = None) -> bool:
        if self.color_mode in {"1", "true", "yes", "always"}:
            return True
        if self.color_mode in {"0", "false", "no", "never"}:
            return False
        if self.no_color:
            return False
        target = stream if stream is not None else sys.stderr
        return hasattr(target, "isatty") and target.isatty()
