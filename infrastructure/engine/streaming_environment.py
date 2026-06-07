"""Environment-backed streaming runtime configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: str = "") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class StreamingEnvironmentSettings:
    """Typed view of streaming runtime flags."""

    verbose_chunks: bool = False

    @classmethod
    def from_env(cls) -> "StreamingEnvironmentSettings":
        return cls(verbose_chunks=_env_flag("PLOTPILOT_VERBOSE_STREAMING"))
