from queue import Empty, Full

from application.engine.services.streaming_bus import StreamingBus
import application.engine.services.streaming_bus as streaming_bus_module


class _FakeQueue:
    def __init__(self, items, capacity):
        self.items = list(items)
        self.capacity = capacity
        self.fail_first_put = True

    def put_nowait(self, item):
        if self.fail_first_put:
            self.fail_first_put = False
            raise Full
        if len(self.items) >= self.capacity:
            raise Full
        self.items.append(item)

    def get_nowait(self):
        if not self.items:
            raise Empty
        return self.items.pop(0)


def test_publish_only_evicts_messages_for_same_novel(monkeypatch):
    fake_queue = _FakeQueue(
        items=[
            {"novel_id": "novel-a", "chunk": "old-a-1"},
            {"novel_id": "novel-b", "chunk": "keep-b"},
            {"novel_id": "novel-a", "chunk": "old-a-2"},
        ],
        capacity=3,
    )
    monkeypatch.setattr(streaming_bus_module, "_get_queue", lambda: fake_queue)

    bus = StreamingBus()
    bus.publish("novel-a", "new-a")

    assert fake_queue.items == [
        {"novel_id": "novel-b", "chunk": "keep-b"},
        {"novel_id": "novel-a", "chunk": "new-a"},
    ]
