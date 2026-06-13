"""Runtime settings for MemoryEngine state cache governance."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    non_negative_float,
    non_negative_int,
    section_value,
)


@dataclass(frozen=True)
class MemoryEngineRuntimeSettings:
    state_cache_ttl_seconds: float = 300.0
    state_cache_max_size: int = 256


def get_memory_engine_runtime_settings() -> MemoryEngineRuntimeSettings:
    section = getattr(get_config(), "memory_engine", None)
    defaults = MemoryEngineRuntimeSettings()
    return MemoryEngineRuntimeSettings(
        state_cache_ttl_seconds=non_negative_float(
            section_value(
                section,
                "state_cache_ttl_seconds",
                defaults.state_cache_ttl_seconds,
            ),
            defaults.state_cache_ttl_seconds,
        ),
        state_cache_max_size=non_negative_int(
            section_value(
                section,
                "state_cache_max_size",
                defaults.state_cache_max_size,
            ),
            defaults.state_cache_max_size,
        ),
    )
