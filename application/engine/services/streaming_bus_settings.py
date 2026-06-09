"""Runtime tuning for the cross-process streaming bus."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    positive_int,
    section_value,
)


@dataclass(frozen=True)
class StreamingBusSettings:
    queue_max_size: int = 10000
    max_batch_chunks: int = 200
    control_scan_limit: int = 50
    audit_overflow_drop_count: int = 10
    stop_overflow_drop_count: int = 100
    start_overflow_drop_count: int = 50
    clear_scan_limit: int = 1000


def get_streaming_bus_settings() -> StreamingBusSettings:
    section = getattr(get_config(), "streaming_bus", None)
    defaults = StreamingBusSettings()
    return StreamingBusSettings(
        queue_max_size=positive_int(
            section_value(section, "queue_max_size", defaults.queue_max_size),
            defaults.queue_max_size,
        ),
        max_batch_chunks=positive_int(
            section_value(section, "max_batch_chunks", defaults.max_batch_chunks),
            defaults.max_batch_chunks,
        ),
        control_scan_limit=positive_int(
            section_value(section, "control_scan_limit", defaults.control_scan_limit),
            defaults.control_scan_limit,
        ),
        audit_overflow_drop_count=positive_int(
            section_value(
                section,
                "audit_overflow_drop_count",
                defaults.audit_overflow_drop_count,
            ),
            defaults.audit_overflow_drop_count,
        ),
        stop_overflow_drop_count=positive_int(
            section_value(
                section,
                "stop_overflow_drop_count",
                defaults.stop_overflow_drop_count,
            ),
            defaults.stop_overflow_drop_count,
        ),
        start_overflow_drop_count=positive_int(
            section_value(
                section,
                "start_overflow_drop_count",
                defaults.start_overflow_drop_count,
            ),
            defaults.start_overflow_drop_count,
        ),
        clear_scan_limit=positive_int(
            section_value(section, "clear_scan_limit", defaults.clear_scan_limit),
            defaults.clear_scan_limit,
        ),
    )
