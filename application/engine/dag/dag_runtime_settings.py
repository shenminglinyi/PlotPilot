"""Runtime tuning for DAG daemon internals."""

from __future__ import annotations

from dataclasses import dataclass

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import positive_float, section_value


@dataclass(frozen=True)
class DAGEventAggregatorSettings:
    flush_interval_seconds: float = 0.5
    stop_join_timeout_seconds: float = 2.0


def get_dag_event_aggregator_settings() -> DAGEventAggregatorSettings:
    dag_engine = getattr(get_config(), "dag_engine", None)
    section = getattr(dag_engine, "event_aggregator", None)
    defaults = DAGEventAggregatorSettings()
    return DAGEventAggregatorSettings(
        flush_interval_seconds=positive_float(
            section_value(
                section,
                "flush_interval_seconds",
                defaults.flush_interval_seconds,
            ),
            defaults.flush_interval_seconds,
        ),
        stop_join_timeout_seconds=positive_float(
            section_value(
                section,
                "stop_join_timeout_seconds",
                defaults.stop_join_timeout_seconds,
            ),
            defaults.stop_join_timeout_seconds,
        ),
    )
