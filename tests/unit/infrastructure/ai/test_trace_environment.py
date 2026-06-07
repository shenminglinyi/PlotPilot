from infrastructure.ai.trace_environment import TraceEnvironmentSettings


def test_trace_environment_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("AI_TRACE_ENABLED", raising=False)

    settings = TraceEnvironmentSettings.from_env()

    assert settings.enabled is True


def test_trace_environment_accepts_disabled_values(monkeypatch):
    for value in ("0", "false", "off", "no"):
        monkeypatch.setenv("AI_TRACE_ENABLED", value)

        assert TraceEnvironmentSettings.from_env().enabled is False


def test_trace_environment_keeps_unknown_values_enabled(monkeypatch):
    monkeypatch.setenv("AI_TRACE_ENABLED", "debug")

    settings = TraceEnvironmentSettings.from_env()

    assert settings.enabled is True
