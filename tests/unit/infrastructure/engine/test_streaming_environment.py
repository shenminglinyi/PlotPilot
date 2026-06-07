from infrastructure.engine.streaming_environment import StreamingEnvironmentSettings


def test_streaming_environment_defaults_to_quiet(monkeypatch):
    monkeypatch.delenv("PLOTPILOT_VERBOSE_STREAMING", raising=False)

    settings = StreamingEnvironmentSettings.from_env()

    assert settings.verbose_chunks is False


def test_streaming_environment_accepts_truthy_values(monkeypatch):
    for value in ("1", "true", "yes"):
        monkeypatch.setenv("PLOTPILOT_VERBOSE_STREAMING", value)

        assert StreamingEnvironmentSettings.from_env().verbose_chunks is True


def test_streaming_environment_rejects_falsey_values(monkeypatch):
    for value in ("", "0", "false", "no"):
        monkeypatch.setenv("PLOTPILOT_VERBOSE_STREAMING", value)

        assert StreamingEnvironmentSettings.from_env().verbose_chunks is False
