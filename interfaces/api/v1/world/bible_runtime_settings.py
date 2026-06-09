"""Runtime settings for Bible and worldbuilding endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    non_negative_float,
    section_value,
)


@dataclass(frozen=True)
class BibleRuntimeSettings:
    worldbuilding_field_emit_delay_seconds: float = 0.02
    worldbuilding_dimension_emit_delay_seconds: float = 0.05


def get_bible_runtime_settings() -> BibleRuntimeSettings:
    bible = getattr(get_config(), "bible", None)
    section = getattr(bible, "runtime", None)
    defaults = BibleRuntimeSettings()
    return BibleRuntimeSettings(
        worldbuilding_field_emit_delay_seconds=non_negative_float(
            section_value(
                section,
                "worldbuilding_field_emit_delay_seconds",
                defaults.worldbuilding_field_emit_delay_seconds,
            ),
            defaults.worldbuilding_field_emit_delay_seconds,
        ),
        worldbuilding_dimension_emit_delay_seconds=non_negative_float(
            section_value(
                section,
                "worldbuilding_dimension_emit_delay_seconds",
                defaults.worldbuilding_dimension_emit_delay_seconds,
            ),
            defaults.worldbuilding_dimension_emit_delay_seconds,
        ),
    )
