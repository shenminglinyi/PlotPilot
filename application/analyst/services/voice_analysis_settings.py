"""Runtime settings for voice analysis caches."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    non_negative_float,
    non_negative_int,
    section_value,
)


@dataclass(frozen=True)
class VoiceAnalysisRuntimeSettings:
    style_cache_ttl_seconds: float = 300.0
    style_cache_max_size: int = 512
    baseline_cache_ttl_seconds: float = 600.0
    baseline_cache_max_size: int = 256


def get_voice_analysis_runtime_settings() -> VoiceAnalysisRuntimeSettings:
    analyst = getattr(get_config(), "analyst", None)
    section = getattr(analyst, "voice_analysis", None)
    defaults = VoiceAnalysisRuntimeSettings()
    return VoiceAnalysisRuntimeSettings(
        style_cache_ttl_seconds=non_negative_float(
            section_value(
                section,
                "style_cache_ttl_seconds",
                defaults.style_cache_ttl_seconds,
            ),
            defaults.style_cache_ttl_seconds,
        ),
        style_cache_max_size=non_negative_int(
            section_value(section, "style_cache_max_size", defaults.style_cache_max_size),
            defaults.style_cache_max_size,
        ),
        baseline_cache_ttl_seconds=non_negative_float(
            section_value(
                section,
                "baseline_cache_ttl_seconds",
                defaults.baseline_cache_ttl_seconds,
            ),
            defaults.baseline_cache_ttl_seconds,
        ),
        baseline_cache_max_size=non_negative_int(
            section_value(
                section,
                "baseline_cache_max_size",
                defaults.baseline_cache_max_size,
            ),
            defaults.baseline_cache_max_size,
        ),
    )
