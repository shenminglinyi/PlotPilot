from queue import Empty, Full

from application.core.config.config_loader import reload_config
from application.engine.services import streaming_bus as streaming_bus_module
from application.engine.services.streaming_bus import StreamingBus
from application.engine.services.streaming_bus_settings import (
    StreamingBusSettings,
    get_streaming_bus_settings,
)


class _FakeQueue:
    def __init__(self, maxsize: int | None = None):
        self.items = []
        self.maxsize = maxsize

    def put_nowait(self, item):
        if self.maxsize is not None and len(self.items) >= self.maxsize:
            raise Full
        self.items.append(item)

    def get_nowait(self):
        if not self.items:
            raise Empty
        return self.items.pop(0)

    def qsize(self):
        return len(self.items)


def test_streaming_bus_uses_injected_verbose_flag(monkeypatch):
    monkeypatch.setenv("PLOTPILOT_VERBOSE_STREAMING", "yes")

    bus = StreamingBus(queue=_FakeQueue(), verbose_chunks=False)

    assert bus._verbose_chunks is False


def test_streaming_bus_reads_environment_when_not_injected(monkeypatch):
    monkeypatch.setenv("PLOTPILOT_VERBOSE_STREAMING", "yes")

    bus = StreamingBus(queue=_FakeQueue())

    assert bus._verbose_chunks is True


def test_streaming_bus_publish_and_batch_with_fake_queue():
    queue = _FakeQueue()
    bus = StreamingBus(queue=queue, verbose_chunks=False)

    bus.publish("novel-1", "hello")
    bus.publish("novel-2", "other")
    result = bus.get_chunks_batch("novel-1")

    assert result == {"deltas": ["hello"], "content": None}
    assert queue.items[0]["novel_id"] == "novel-2"


def test_inject_stream_queue_preserves_existing_compatibility():
    queue = _FakeQueue()

    streaming_bus_module.inject_stream_queue(queue)

    assert streaming_bus_module.get_stream_queue() is queue


def test_streaming_bus_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
streaming_bus:
  queue_max_size: 123
  max_batch_chunks: 7
  control_scan_limit: 6
  audit_overflow_drop_count: 5
  stop_overflow_drop_count: 4
  start_overflow_drop_count: 3
  clear_scan_limit: 2
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_streaming_bus_settings()

        assert settings.queue_max_size == 123
        assert settings.max_batch_chunks == 7
        assert settings.control_scan_limit == 6
        assert settings.audit_overflow_drop_count == 5
        assert settings.stop_overflow_drop_count == 4
        assert settings.start_overflow_drop_count == 3
        assert settings.clear_scan_limit == 2
    finally:
        reload_config()


def test_streaming_bus_overflow_drop_count_is_configurable():
    queue = _FakeQueue(maxsize=1)
    bus = StreamingBus(
        queue=queue,
        verbose_chunks=False,
        settings=StreamingBusSettings(audit_overflow_drop_count=0),
    )

    bus.publish("novel-1", "old")
    bus.publish_audit_event("novel-1", "audit_start")
    assert queue.items[0].get("chunk") == "old"

    bus = StreamingBus(
        queue=queue,
        verbose_chunks=False,
        settings=StreamingBusSettings(audit_overflow_drop_count=1),
    )
    bus.publish_audit_event("novel-1", "audit_start")

    assert queue.items[0]["type"] == "audit_event"
    assert queue.items[0]["event_type"] == "audit_start"
