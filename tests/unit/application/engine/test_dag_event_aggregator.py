import time

import pytest

from application.core.config.config_loader import reload_config
from application.engine.dag.dag_runtime_settings import get_dag_event_aggregator_settings
from application.engine.dag.event_aggregator import NodeEventAggregator
from application.engine.dag.models import NodeEvent


def test_dag_event_aggregator_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
dag_engine:
  event_aggregator:
    flush_interval_seconds: 0.02
    stop_join_timeout_seconds: 0.03
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_dag_event_aggregator_settings()

        assert settings.flush_interval_seconds == pytest.approx(0.02)
        assert settings.stop_join_timeout_seconds == pytest.approx(0.03)
    finally:
        reload_config()


def test_node_event_aggregator_stop_wakes_sleeping_flush_loop(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
dag_engine:
  event_aggregator:
    flush_interval_seconds: 5.0
    stop_join_timeout_seconds: 0.5
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        collected = []
        aggregator = NodeEventAggregator()
        aggregator.set_flush_callback(lambda events: collected.extend(events))
        aggregator.push(NodeEvent(type="node_status_change", novel_id="n1", node_id="n1"))

        aggregator.start()
        started = time.monotonic()
        aggregator.stop()

        assert time.monotonic() - started < 0.5
        assert len(collected) == 1
    finally:
        reload_config()
