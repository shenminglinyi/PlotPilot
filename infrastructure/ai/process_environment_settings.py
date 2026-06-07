"""Environment-backed process bootstrap settings for local AI dependencies."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: str = "false") -> bool:
    return (os.getenv(name, default) or "").strip().lower() == "true"


@dataclass(frozen=True)
class ProcessEnvironmentSettings:
    """Typed view of process-level AI bootstrap flags."""

    disable_ssl_verify: bool = False

    @classmethod
    def from_env(cls) -> "ProcessEnvironmentSettings":
        return cls(disable_ssl_verify=_env_flag("DISABLE_SSL_VERIFY", "false"))
