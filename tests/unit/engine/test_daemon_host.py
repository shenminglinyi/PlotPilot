"""DaemonHostMixin Phase 7/8/9 测试"""
import pytest

from application.engine.services.autopilot_daemon import AutopilotDaemon
from engine.runtime.daemon_host import DaemonHostMixin
from engine.runtime.runner import StoryPipelineRunner


def test_autopilot_daemon_inherits_daemon_host_mixin():
    assert issubclass(AutopilotDaemon, DaemonHostMixin)


def test_story_pipeline_runner_inherits_daemon_host_mixin():
    assert issubclass(StoryPipelineRunner, DaemonHostMixin)


def test_daemon_host_mixin_provides_infrastructure_methods():
    assert hasattr(DaemonHostMixin, "_update_shared_state")
    assert hasattr(DaemonHostMixin, "_call_with_timeout")
    assert hasattr(DaemonHostMixin, "_find_next_unwritten_chapter_async")
    assert hasattr(DaemonHostMixin, "_flush_novel")


def test_autopilot_daemon_keeps_entrypoint_methods():
    assert hasattr(AutopilotDaemon, "run_forever")
    assert hasattr(AutopilotDaemon, "_process_novel")
    assert hasattr(AutopilotDaemon, "_handle_writing")


def test_autopilot_daemon_emits_deprecation_warning():
    with pytest.warns(DeprecationWarning, match="AutopilotDaemon"):
        AutopilotDaemon(
            novel_repository=object(),
            llm_service=object(),
            context_builder=None,
            background_task_service=None,
            planning_service=None,
            story_node_repo=None,
            chapter_repository=None,
        )


def test_story_pipeline_runner_is_self_hosted():
    runner = StoryPipelineRunner(
        novel_repository=object(),
        llm_service=object(),
        context_builder=None,
        background_task_service=None,
        planning_service=None,
        story_node_repo=None,
        chapter_repository=None,
        use_story_pipeline_for_writing=True,
    )
    assert runner.host is runner
    assert runner.use_story_pipeline_for_writing is True

