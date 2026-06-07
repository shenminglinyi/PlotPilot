"""Environment-backed DAG runtime configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: str = "false") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class DAGEnvironmentSettings:
    """Typed view of DAG runtime feature flags."""

    enabled: bool = False

    @classmethod
    def from_env(cls) -> "DAGEnvironmentSettings":
        return cls(enabled=_env_flag("ENABLE_DAG_ENGINE", "false"))
