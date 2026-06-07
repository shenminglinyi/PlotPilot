from infrastructure.engine.story_pipeline_environment import (
    StoryPipelineEnvironmentSettings,
)


def test_story_pipeline_environment_defaults_to_writing(monkeypatch):
    monkeypatch.delenv("PLOTPILOT_USE_STORY_PIPELINE", raising=False)

    settings = StoryPipelineEnvironmentSettings.from_env()

    assert settings.raw_mode == ""
    assert settings.mode == "writing"
    assert settings.is_unset is True
    assert settings.is_unknown is False


def test_story_pipeline_environment_off_aliases():
    for raw in ("off", "legacy", "false", "0", "no"):
        settings = StoryPipelineEnvironmentSettings(raw_mode=raw)

        assert settings.mode == "off"
        assert settings.is_unknown is False


def test_story_pipeline_environment_full_aliases():
    for raw in ("full", "all", "engine"):
        settings = StoryPipelineEnvironmentSettings(raw_mode=raw)

        assert settings.mode == "full"
        assert settings.is_unknown is False


def test_story_pipeline_environment_writing_aliases():
    for raw in ("1", "true", "yes", "on", "writing"):
        settings = StoryPipelineEnvironmentSettings(raw_mode=raw)

        assert settings.mode == "writing"
        assert settings.is_unknown is False


def test_story_pipeline_environment_unknown_defaults_to_writing():
    settings = StoryPipelineEnvironmentSettings(raw_mode="surprise")

    assert settings.mode == "writing"
    assert settings.is_unknown is True
