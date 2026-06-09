"""Runtime settings for cast graph derivation and cache behavior."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    non_negative_float,
    non_negative_int,
    section_value,
)


@dataclass(frozen=True)
class CastRuntimeSettings:
    graph_cache_ttl_seconds: float = 8.0
    graph_cache_max_size: int = 128


def get_cast_runtime_settings() -> CastRuntimeSettings:
    world = getattr(get_config(), "world", None)
    cast = getattr(world, "cast", None)
    section = getattr(cast, "runtime", None)
    defaults = CastRuntimeSettings()
    return CastRuntimeSettings(
        graph_cache_ttl_seconds=non_negative_float(
            section_value(
                section,
                "graph_cache_ttl_seconds",
                defaults.graph_cache_ttl_seconds,
            ),
            defaults.graph_cache_ttl_seconds,
        ),
        graph_cache_max_size=non_negative_int(
            section_value(section, "graph_cache_max_size", defaults.graph_cache_max_size),
            defaults.graph_cache_max_size,
        ),
    )
