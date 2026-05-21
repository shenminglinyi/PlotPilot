"""EngineDaemon Phase 8/9 测试"""
from unittest.mock import MagicMock, patch

import pytest

from engine.runtime.engine_daemon import EngineDaemon


def test_engine_daemon_creates_runner_with_story_pipeline():
    with patch("engine.runtime.runner.StoryPipelineRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        daemon = EngineDaemon(
            novel_repository="repo",
            llm_service="llm",
            use_story_pipeline_for_writing=True,
        )

        mock_runner_cls.assert_called_once()
        assert mock_runner_cls.call_args.kwargs["use_story_pipeline_for_writing"] is True
        assert daemon.runner is mock_runner
        assert daemon.inner is mock_runner
        assert daemon.use_story_pipeline_for_writing is True


def test_engine_daemon_legacy_writing_when_flag_false():
    with patch("engine.runtime.runner.StoryPipelineRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        daemon = EngineDaemon(
            novel_repository="repo",
            use_story_pipeline_for_writing=False,
        )

        assert mock_runner_cls.call_args.kwargs["use_story_pipeline_for_writing"] is False
        assert daemon.use_story_pipeline_for_writing is False


def test_engine_daemon_infers_writing_from_env(monkeypatch):
    monkeypatch.setenv("PLOTPILOT_USE_STORY_PIPELINE", "writing")

    with patch("engine.runtime.runner.StoryPipelineRunner") as mock_runner_cls:
        mock_runner_cls.return_value = MagicMock()
        EngineDaemon(novel_repository="repo")
        assert mock_runner_cls.call_args.kwargs["use_story_pipeline_for_writing"] is True


def test_engine_daemon_defaults_story_pipeline_when_env_unset(monkeypatch):
    monkeypatch.delenv("PLOTPILOT_USE_STORY_PIPELINE", raising=False)

    with patch("engine.runtime.runner.StoryPipelineRunner") as mock_runner_cls:
        mock_runner_cls.return_value = MagicMock()
        EngineDaemon(novel_repository="repo")
        assert mock_runner_cls.call_args.kwargs["use_story_pipeline_for_writing"] is True


def test_engine_daemon_run_forever_delegates_to_runner():
    with patch("engine.runtime.runner.StoryPipelineRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        daemon = EngineDaemon(novel_repository="repo")
        daemon.run_forever()
        mock_runner.run_forever.assert_called_once()
