from infrastructure.ai.trace_recorder import TraceRecorder


def test_trace_recorder_uses_environment_enabled_flag(monkeypatch):
    monkeypatch.setenv("AI_TRACE_ENABLED", "no")

    recorder = TraceRecorder()

    assert recorder.enabled is False


def test_trace_recorder_explicit_enabled_takes_precedence(monkeypatch):
    monkeypatch.setenv("AI_TRACE_ENABLED", "no")

    recorder = TraceRecorder(enabled=True)

    assert recorder.enabled is True


def test_trace_recorder_disabled_returns_none_without_store():
    recorder = TraceRecorder(enabled=False)

    assert recorder.record_span(phase="prompt_render") is None
