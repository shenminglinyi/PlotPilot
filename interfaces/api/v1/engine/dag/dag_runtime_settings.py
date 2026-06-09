"""Runtime settings for DAG display and SSE endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    positive_float,
    positive_int,
    section_value,
)


@dataclass(frozen=True)
class DAGRuntimeSettings:
    sse_queue_size: int = 100
    sse_idle_poll_seconds: float = 1.0
    sse_heartbeat_every_idle_ticks: int = 30
    dag_cache_max_size: int = 256


def get_dag_runtime_settings() -> DAGRuntimeSettings:
    dag_engine = getattr(get_config(), "dag_engine", None)
    sse_section = getattr(dag_engine, "sse", None)
    cache_section = getattr(dag_engine, "cache", None)
    defaults = DAGRuntimeSettings()
    return DAGRuntimeSettings(
        sse_queue_size=positive_int(
            section_value(sse_section, "queue_size", defaults.sse_queue_size),
            defaults.sse_queue_size,
        ),
        sse_idle_poll_seconds=positive_float(
            section_value(sse_section, "idle_poll_seconds", defaults.sse_idle_poll_seconds),
            defaults.sse_idle_poll_seconds,
        ),
        sse_heartbeat_every_idle_ticks=positive_int(
            section_value(
                sse_section,
                "heartbeat_every_idle_ticks",
                defaults.sse_heartbeat_every_idle_ticks,
            ),
            defaults.sse_heartbeat_every_idle_ticks,
        ),
        dag_cache_max_size=positive_int(
            section_value(cache_section, "max_size", defaults.dag_cache_max_size),
            defaults.dag_cache_max_size,
        ),
    )
