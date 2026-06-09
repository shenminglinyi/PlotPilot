"""Runtime tuning for autopilot HTTP and SSE endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    positive_float,
    positive_int,
    section_value,
)


@dataclass(frozen=True)
class AutopilotRuntimeSettings:
    sse_thread_pool_workers: int = 12
    shared_state_cache_ttl_seconds: float = 1.0
    shared_state_cache_max_size: int = 1000
    sse_max_lifetime_seconds: float = 7200.0
    db_read_timeout_seconds: float = 5.0
    db_persist_timeout_seconds: float = 30.0
    persistence_idle_timeout_seconds: float = 5.0
    persistence_fallback_idle_timeout_seconds: float = 3.0
    sse_tick_timeout_seconds: float = 2.0
    sse_missing_check_timeout_seconds: float = 1.0
    log_poll_seconds: float = 2.0
    log_missing_keepalive_seconds: float = 3.0
    log_heartbeat_every_ticks: int = 10
    log_stream_max_events: int = 200
    chapter_active_poll_seconds: float = 0.8
    chapter_slow_poll_seconds: float = 3.0
    chapter_heartbeat_every_ticks: int = 10
    chapter_empty_status_check_polls: int = 24
    chapter_stream_max_chunks: int = 50
    events_poll_seconds: float = 3.0


def get_autopilot_runtime_settings() -> AutopilotRuntimeSettings:
    autopilot = getattr(get_config(), "autopilot", None)
    section = getattr(autopilot, "runtime", None)
    defaults = AutopilotRuntimeSettings()
    return AutopilotRuntimeSettings(
        sse_thread_pool_workers=positive_int(
            section_value(section, "sse_thread_pool_workers", defaults.sse_thread_pool_workers),
            defaults.sse_thread_pool_workers,
        ),
        shared_state_cache_ttl_seconds=positive_float(
            section_value(
                section,
                "shared_state_cache_ttl_seconds",
                defaults.shared_state_cache_ttl_seconds,
            ),
            defaults.shared_state_cache_ttl_seconds,
        ),
        shared_state_cache_max_size=positive_int(
            section_value(
                section,
                "shared_state_cache_max_size",
                defaults.shared_state_cache_max_size,
            ),
            defaults.shared_state_cache_max_size,
        ),
        sse_max_lifetime_seconds=positive_float(
            section_value(section, "sse_max_lifetime_seconds", defaults.sse_max_lifetime_seconds),
            defaults.sse_max_lifetime_seconds,
        ),
        db_read_timeout_seconds=positive_float(
            section_value(section, "db_read_timeout_seconds", defaults.db_read_timeout_seconds),
            defaults.db_read_timeout_seconds,
        ),
        db_persist_timeout_seconds=positive_float(
            section_value(section, "db_persist_timeout_seconds", defaults.db_persist_timeout_seconds),
            defaults.db_persist_timeout_seconds,
        ),
        persistence_idle_timeout_seconds=positive_float(
            section_value(
                section,
                "persistence_idle_timeout_seconds",
                defaults.persistence_idle_timeout_seconds,
            ),
            defaults.persistence_idle_timeout_seconds,
        ),
        persistence_fallback_idle_timeout_seconds=positive_float(
            section_value(
                section,
                "persistence_fallback_idle_timeout_seconds",
                defaults.persistence_fallback_idle_timeout_seconds,
            ),
            defaults.persistence_fallback_idle_timeout_seconds,
        ),
        sse_tick_timeout_seconds=positive_float(
            section_value(section, "sse_tick_timeout_seconds", defaults.sse_tick_timeout_seconds),
            defaults.sse_tick_timeout_seconds,
        ),
        sse_missing_check_timeout_seconds=positive_float(
            section_value(
                section,
                "sse_missing_check_timeout_seconds",
                defaults.sse_missing_check_timeout_seconds,
            ),
            defaults.sse_missing_check_timeout_seconds,
        ),
        log_poll_seconds=positive_float(
            section_value(section, "log_poll_seconds", defaults.log_poll_seconds),
            defaults.log_poll_seconds,
        ),
        log_missing_keepalive_seconds=positive_float(
            section_value(
                section,
                "log_missing_keepalive_seconds",
                defaults.log_missing_keepalive_seconds,
            ),
            defaults.log_missing_keepalive_seconds,
        ),
        log_heartbeat_every_ticks=positive_int(
            section_value(section, "log_heartbeat_every_ticks", defaults.log_heartbeat_every_ticks),
            defaults.log_heartbeat_every_ticks,
        ),
        log_stream_max_events=positive_int(
            section_value(section, "log_stream_max_events", defaults.log_stream_max_events),
            defaults.log_stream_max_events,
        ),
        chapter_active_poll_seconds=positive_float(
            section_value(
                section,
                "chapter_active_poll_seconds",
                defaults.chapter_active_poll_seconds,
            ),
            defaults.chapter_active_poll_seconds,
        ),
        chapter_slow_poll_seconds=positive_float(
            section_value(section, "chapter_slow_poll_seconds", defaults.chapter_slow_poll_seconds),
            defaults.chapter_slow_poll_seconds,
        ),
        chapter_heartbeat_every_ticks=positive_int(
            section_value(
                section,
                "chapter_heartbeat_every_ticks",
                defaults.chapter_heartbeat_every_ticks,
            ),
            defaults.chapter_heartbeat_every_ticks,
        ),
        chapter_empty_status_check_polls=positive_int(
            section_value(
                section,
                "chapter_empty_status_check_polls",
                defaults.chapter_empty_status_check_polls,
            ),
            defaults.chapter_empty_status_check_polls,
        ),
        chapter_stream_max_chunks=positive_int(
            section_value(section, "chapter_stream_max_chunks", defaults.chapter_stream_max_chunks),
            defaults.chapter_stream_max_chunks,
        ),
        events_poll_seconds=positive_float(
            section_value(section, "events_poll_seconds", defaults.events_poll_seconds),
            defaults.events_poll_seconds,
        ),
    )
