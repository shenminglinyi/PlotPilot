"""Runtime settings for planning SSE presentation."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import (
    positive_float,
    positive_int,
    section_value,
)


@dataclass(frozen=True)
class PlanningRuntimeSettings:
    macro_generation_poll_seconds: float = 0.4
    macro_part_node_delay_seconds: float = 0.09
    macro_volume_node_delay_seconds: float = 0.06
    macro_act_node_delay_seconds: float = 0.04
    macro_watch_poll_seconds: float = 0.32
    macro_watch_node_delay_seconds: float = 0.028
    macro_watch_max_seconds: float = 3600.0
    macro_watch_heartbeat_every_ticks: int = 10
    act_generation_poll_seconds: float = 0.4
    act_chapter_node_delay_seconds: float = 0.045
    act_generation_progress_base_percent: int = 8
    act_generation_progress_step_percent: int = 3
    act_generation_progress_cycle_ticks: int = 10
    act_generation_progress_max_percent: int = 88


def get_planning_runtime_settings() -> PlanningRuntimeSettings:
    planning = getattr(get_config(), "planning", None)
    section = getattr(planning, "runtime", None)
    defaults = PlanningRuntimeSettings()
    return PlanningRuntimeSettings(
        macro_generation_poll_seconds=positive_float(
            section_value(
                section,
                "macro_generation_poll_seconds",
                defaults.macro_generation_poll_seconds,
            ),
            defaults.macro_generation_poll_seconds,
        ),
        macro_part_node_delay_seconds=positive_float(
            section_value(
                section,
                "macro_part_node_delay_seconds",
                defaults.macro_part_node_delay_seconds,
            ),
            defaults.macro_part_node_delay_seconds,
        ),
        macro_volume_node_delay_seconds=positive_float(
            section_value(
                section,
                "macro_volume_node_delay_seconds",
                defaults.macro_volume_node_delay_seconds,
            ),
            defaults.macro_volume_node_delay_seconds,
        ),
        macro_act_node_delay_seconds=positive_float(
            section_value(
                section,
                "macro_act_node_delay_seconds",
                defaults.macro_act_node_delay_seconds,
            ),
            defaults.macro_act_node_delay_seconds,
        ),
        macro_watch_poll_seconds=positive_float(
            section_value(section, "macro_watch_poll_seconds", defaults.macro_watch_poll_seconds),
            defaults.macro_watch_poll_seconds,
        ),
        macro_watch_node_delay_seconds=positive_float(
            section_value(
                section,
                "macro_watch_node_delay_seconds",
                defaults.macro_watch_node_delay_seconds,
            ),
            defaults.macro_watch_node_delay_seconds,
        ),
        macro_watch_max_seconds=positive_float(
            section_value(section, "macro_watch_max_seconds", defaults.macro_watch_max_seconds),
            defaults.macro_watch_max_seconds,
        ),
        macro_watch_heartbeat_every_ticks=positive_int(
            section_value(
                section,
                "macro_watch_heartbeat_every_ticks",
                defaults.macro_watch_heartbeat_every_ticks,
            ),
            defaults.macro_watch_heartbeat_every_ticks,
        ),
        act_generation_poll_seconds=positive_float(
            section_value(
                section,
                "act_generation_poll_seconds",
                defaults.act_generation_poll_seconds,
            ),
            defaults.act_generation_poll_seconds,
        ),
        act_chapter_node_delay_seconds=positive_float(
            section_value(
                section,
                "act_chapter_node_delay_seconds",
                defaults.act_chapter_node_delay_seconds,
            ),
            defaults.act_chapter_node_delay_seconds,
        ),
        act_generation_progress_base_percent=positive_int(
            section_value(
                section,
                "act_generation_progress_base_percent",
                defaults.act_generation_progress_base_percent,
            ),
            defaults.act_generation_progress_base_percent,
        ),
        act_generation_progress_step_percent=positive_int(
            section_value(
                section,
                "act_generation_progress_step_percent",
                defaults.act_generation_progress_step_percent,
            ),
            defaults.act_generation_progress_step_percent,
        ),
        act_generation_progress_cycle_ticks=positive_int(
            section_value(
                section,
                "act_generation_progress_cycle_ticks",
                defaults.act_generation_progress_cycle_ticks,
            ),
            defaults.act_generation_progress_cycle_ticks,
        ),
        act_generation_progress_max_percent=positive_int(
            section_value(
                section,
                "act_generation_progress_max_percent",
                defaults.act_generation_progress_max_percent,
            ),
            defaults.act_generation_progress_max_percent,
        ),
    )
