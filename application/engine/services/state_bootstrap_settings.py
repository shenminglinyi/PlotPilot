"""Runtime tuning for shared-state bootstrap work."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import positive_float, section_value


@dataclass(frozen=True)
class StateBootstrapSettings:
    triple_fetch_timeout_seconds: float = 5.0


def get_state_bootstrap_settings() -> StateBootstrapSettings:
    section = getattr(get_config(), "state_bootstrap", None)
    defaults = StateBootstrapSettings()
    return StateBootstrapSettings(
        triple_fetch_timeout_seconds=positive_float(
            section_value(
                section,
                "triple_fetch_timeout_seconds",
                defaults.triple_fetch_timeout_seconds,
            ),
            defaults.triple_fetch_timeout_seconds,
        ),
    )
