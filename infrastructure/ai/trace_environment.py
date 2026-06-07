"""Environment-backed AI trace configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag_enabled(name: str, default: str = "true") -> bool:
    return (os.getenv(name, default) or "").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


@dataclass(frozen=True)
class TraceEnvironmentSettings:
    """Typed view of AI trace runtime flags."""

    enabled: bool = True

    @classmethod
    def from_env(cls) -> "TraceEnvironmentSettings":
        return cls(enabled=_env_flag_enabled("AI_TRACE_ENABLED", "true"))
