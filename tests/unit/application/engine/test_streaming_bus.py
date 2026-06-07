from queue import Empty, Full

from application.engine.services import streaming_bus as streaming_bus_module
from application.engine.services.streaming_bus import StreamingBus


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
