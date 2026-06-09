"""Runtime tuning for structured JSON generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import positive_float, section_value


@dataclass(frozen=True)
class StructuredJSONSettings:
    retry_backoff_base_seconds: float = 1.5
    retry_backoff_max_seconds: float = 8.0


def get_structured_json_settings() -> StructuredJSONSettings:
    ai = getattr(get_config(), "ai", None)
    section = getattr(ai, "structured_json", None)
    defaults = StructuredJSONSettings()
    return StructuredJSONSettings(
        retry_backoff_base_seconds=positive_float(
            section_value(
                section,
                "retry_backoff_base_seconds",
                defaults.retry_backoff_base_seconds,
            ),
            defaults.retry_backoff_base_seconds,
        ),
        retry_backoff_max_seconds=positive_float(
            section_value(
                section,
                "retry_backoff_max_seconds",
                defaults.retry_backoff_max_seconds,
            ),
            defaults.retry_backoff_max_seconds,
        ),
    )
