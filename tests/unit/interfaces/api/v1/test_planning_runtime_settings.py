import pytest

from application.core.config.config_loader import reload_config
from interfaces.api.v1.blueprint.planning_runtime_settings import (
    get_planning_runtime_settings,
)


def test_planning_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
planning:
  runtime:
    macro_generation_poll_seconds: 0.11
    macro_part_node_delay_seconds: 0.12
    macro_volume_node_delay_seconds: 0.13
    macro_act_node_delay_seconds: 0.14
    macro_watch_poll_seconds: 0.15
    macro_watch_node_delay_seconds: 0.16
    macro_watch_max_seconds: 99
    macro_watch_heartbeat_every_ticks: 6
    act_generation_poll_seconds: 0.17
    act_chapter_node_delay_seconds: 0.18
    act_generation_progress_base_percent: 9
    act_generation_progress_step_percent: 4
    act_generation_progress_cycle_ticks: 8
    act_generation_progress_max_percent: 91
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_planning_runtime_settings()

        assert settings.macro_generation_poll_seconds == pytest.approx(0.11)
        assert settings.macro_part_node_delay_seconds == pytest.approx(0.12)
        assert settings.macro_volume_node_delay_seconds == pytest.approx(0.13)
        assert settings.macro_act_node_delay_seconds == pytest.approx(0.14)
        assert settings.macro_watch_poll_seconds == pytest.approx(0.15)
        assert settings.macro_watch_node_delay_seconds == pytest.approx(0.16)
        assert settings.macro_watch_max_seconds == 99
        assert settings.macro_watch_heartbeat_every_ticks == 6
        assert settings.act_generation_poll_seconds == pytest.approx(0.17)
        assert settings.act_chapter_node_delay_seconds == pytest.approx(0.18)
        assert settings.act_generation_progress_base_percent == 9
        assert settings.act_generation_progress_step_percent == 4
        assert settings.act_generation_progress_cycle_ticks == 8
        assert settings.act_generation_progress_max_percent == 91
    finally:
        reload_config()
