"""Runtime tuning for LLM control workbench endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    non_negative_float,
    positive_int,
    section_value,
)


@dataclass(frozen=True)
class LLMControlRuntimeSettings:
    model_list_timeout_ms: int = 30000
    panel_cache_ttl_seconds: float = 10.0
    plaza_cache_ttl_seconds: float = 60.0


def get_llm_control_runtime_settings() -> LLMControlRuntimeSettings:
    workbench = getattr(get_config(), "workbench", None)
    section = getattr(workbench, "llm_control", None)
    defaults = LLMControlRuntimeSettings()
    return LLMControlRuntimeSettings(
        model_list_timeout_ms=positive_int(
            section_value(section, "model_list_timeout_ms", defaults.model_list_timeout_ms),
            defaults.model_list_timeout_ms,
        ),
        panel_cache_ttl_seconds=non_negative_float(
            section_value(section, "panel_cache_ttl_seconds", defaults.panel_cache_ttl_seconds),
            defaults.panel_cache_ttl_seconds,
        ),
        plaza_cache_ttl_seconds=non_negative_float(
            section_value(section, "plaza_cache_ttl_seconds", defaults.plaza_cache_ttl_seconds),
            defaults.plaza_cache_ttl_seconds,
        ),
    )
