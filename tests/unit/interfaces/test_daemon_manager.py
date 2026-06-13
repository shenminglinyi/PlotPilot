from interfaces.api.settings import BackendSettings
from interfaces.daemon_manager import (
    AutopilotDaemonManager,
    DaemonLifecycleSettings,
    DaemonStatus,
    is_expected_daemon_shutdown_exception,
)


class FakeEvent:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class FakeProcess:
    pid = 1234

    def __init__(self, *, alive=True):
        self.alive = alive
        self.join_calls = []
        self.terminated = False

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)

    def terminate(self):
        self.terminated = True
        self.alive = False


def test_expected_daemon_shutdown_exception_detects_chained_interrupt():
    exc = RuntimeError("wrapper")
    exc.__cause__ = KeyboardInterrupt()

    assert is_expected_daemon_shutdown_exception(exc) is True


def test_daemon_manager_status_reads_process_state():
    process = FakeProcess(alive=True)
    manager = AutopilotDaemonManager(
        log_level=20,
        log_file="logs/test.log",
        shared_state_provider=lambda: {},
        lifecycle_settings_provider=lambda: DaemonLifecycleSettings(
            graceful_join_timeout_seconds=0.25,
            terminate_join_timeout_seconds=0.5,
        ),
    )
    manager.process = process

    assert manager.status() == DaemonStatus(running=True, pid=1234)


def test_daemon_manager_start_respects_disable_auto_daemon():
    calls = []
    manager = AutopilotDaemonManager(
        log_level=20,
        log_file="logs/test.log",
        shared_state_provider=lambda: {},
        settings_provider=lambda: BackendSettings(disable_auto_daemon=True),
        process_factory=lambda **kwargs: calls.append(kwargs),
    )

    manager.start()

    assert calls == []
    assert manager.process is None


def test_daemon_manager_stop_signals_and_terminates_stuck_process(monkeypatch):
    process = FakeProcess(alive=True)
    event = FakeEvent()
    manager = AutopilotDaemonManager(
        log_level=20,
        log_file="logs/test.log",
        shared_state_provider=lambda: {},
        lifecycle_settings_provider=lambda: DaemonLifecycleSettings(
            graceful_join_timeout_seconds=0.25,
            terminate_join_timeout_seconds=0.5,
        ),
    )
    manager.process = process
    manager.stop_event = event
    monkeypatch.setattr("interfaces.daemon_manager.os.name", "posix")

    manager.stop()

    assert event.was_set is True
    assert process.terminated is True
    assert process.join_calls == [0.25, 0.5]
    assert manager.process is None
    assert manager.stop_event is None
