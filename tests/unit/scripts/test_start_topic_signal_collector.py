"""独立市场信号采集脚本测试。"""

from scripts import start_topic_signal_collector


class FakeAutomationService:
    def __init__(self):
        self.run_pending_calls = []
        self.run_forever_calls = []

    def run_pending_once(self, force=False):
        self.run_pending_calls.append(force)
        return True

    def run_forever(self, run_immediately=True):
        self.run_forever_calls.append(run_immediately)


def test_main_runs_one_collection_when_once_is_set(monkeypatch):
    fake_service = FakeAutomationService()
    monkeypatch.setattr(
        start_topic_signal_collector,
        "build_topic_signal_automation_service",
        lambda poll_interval_seconds: fake_service,
    )

    exit_code = start_topic_signal_collector.main(["--once", "--force", "--poll-interval", "12"])

    assert exit_code == 0
    assert fake_service.run_pending_calls == [True]
    assert fake_service.run_forever_calls == []


def test_main_starts_forever_loop_by_default(monkeypatch):
    fake_service = FakeAutomationService()
    poll_intervals = []

    def build_service(poll_interval_seconds):
        poll_intervals.append(poll_interval_seconds)
        return fake_service

    monkeypatch.setattr(
        start_topic_signal_collector,
        "build_topic_signal_automation_service",
        build_service,
    )

    exit_code = start_topic_signal_collector.main(["--poll-interval", "30", "--no-initial-run"])

    assert exit_code == 0
    assert poll_intervals == [30]
    assert fake_service.run_pending_calls == []
    assert fake_service.run_forever_calls == [False]
