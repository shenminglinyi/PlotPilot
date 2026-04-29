"""TopicSignalAutomationService 测试。"""

from application.topic.dtos import (
    TopicMarketSignalAutomationSettingsDTO,
    TopicMarketSignalCollectRequestDTO,
)
from application.topic.services.topic_signal_automation_service import (
    TopicSignalAutomationService,
)


class FakeTopicIdeaService:
    def __init__(self):
        self.settings = TopicMarketSignalAutomationSettingsDTO(
            enabled=True,
            interval_minutes=60,
            limit_per_source=5,
            lookback_days=14,
            selected_source_keys=["qidian_rank"],
            source_weights={"qidian_rank": 1.2},
        )
        self.collected = []

    def get_market_signal_settings(self):
        return self.settings

    def update_market_signal_settings(self, changes):
        for key, value in changes.items():
            setattr(self.settings, key, value)
        return self.settings

    def collect_market_signals(self, request):
        self.collected.append(request)
        return []


class FakeStopEvent:
    def __init__(self, stop_after_waits=1):
        self.stop_after_waits = stop_after_waits
        self.wait_calls = []

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        return len(self.wait_calls) >= self.stop_after_waits


def test_run_pending_once_collects_and_records_success():
    topic_service = FakeTopicIdeaService()
    service = TopicSignalAutomationService(topic_service)

    ran = service.run_pending_once(force=True)

    assert ran is True
    assert topic_service.collected == [
        TopicMarketSignalCollectRequestDTO(
            source_keys=["qidian_rank"],
            limit_per_source=5,
        )
    ]
    assert topic_service.settings.last_status == "success"
    assert topic_service.settings.last_run_at


def test_run_pending_once_skips_when_disabled():
    topic_service = FakeTopicIdeaService()
    topic_service.settings.enabled = False
    service = TopicSignalAutomationService(topic_service)

    ran = service.run_pending_once(force=False)

    assert ran is False
    assert topic_service.collected == []


def test_run_forever_runs_immediately_and_stops_after_wait():
    topic_service = FakeTopicIdeaService()
    service = TopicSignalAutomationService(topic_service, poll_interval_seconds=1)
    stop_event = FakeStopEvent(stop_after_waits=1)

    service.run_forever(stop_event=stop_event, run_immediately=True)

    assert topic_service.collected == [
        TopicMarketSignalCollectRequestDTO(
            source_keys=["qidian_rank"],
            limit_per_source=5,
        )
    ]
    assert stop_event.wait_calls == [10]
