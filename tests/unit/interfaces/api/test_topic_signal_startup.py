import pytest


@pytest.mark.asyncio
async def test_startup_event_does_not_start_topic_signal_automation(monkeypatch):
    from interfaces import main

    started = []

    class FakeTopicSignalAutomationService:
        def start(self):
            started.append("start")

    monkeypatch.setattr(main, "_stop_all_running_novels", lambda: None)
    monkeypatch.setattr(main, "_start_autopilot_daemon_thread", lambda: None)
    monkeypatch.setattr(
        main,
        "get_topic_signal_automation_service",
        lambda: FakeTopicSignalAutomationService(),
    )

    await main.startup_event()

    assert started == []
