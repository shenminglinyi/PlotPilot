from application.engine.services.memory_engine import MemoryEngine, MemoryState
from application.engine.services.memory_engine_settings import MemoryEngineRuntimeSettings


def _engine(*, ttl: float = 100.0, max_size: int = 2) -> MemoryEngine:
    return MemoryEngine(
        llm_service=object(),
        bible_repository=object(),
        runtime_settings=MemoryEngineRuntimeSettings(
            state_cache_ttl_seconds=ttl,
            state_cache_max_size=max_size,
        ),
    )


def test_memory_engine_state_cache_reuses_loaded_state(monkeypatch):
    engine = _engine()
    calls = []

    def load_state(novel_id: str) -> MemoryState:
        calls.append(novel_id)
        return MemoryState(novel_id=novel_id)

    monkeypatch.setattr(engine, "_load_from_db", load_state)

    first = engine._get_or_load_state("n1")
    second = engine._get_or_load_state("n1")

    assert first is second
    assert calls == ["n1"]


def test_memory_engine_state_cache_evicts_lru_entry(monkeypatch):
    engine = _engine(max_size=2)
    calls = []

    def load_state(novel_id: str) -> MemoryState:
        calls.append(novel_id)
        return MemoryState(novel_id=novel_id)

    monkeypatch.setattr(engine, "_load_from_db", load_state)

    engine._get_or_load_state("n1")
    engine._get_or_load_state("n2")
    engine._get_or_load_state("n1")
    engine._get_or_load_state("n3")

    assert calls == ["n1", "n2", "n3"]
    assert list(engine._cache) == ["n1", "n3"]
    assert "n2" not in engine._cache_loaded_at


def test_memory_engine_state_cache_expires(monkeypatch):
    engine = _engine(ttl=1.0, max_size=2)
    now = 10.0
    calls = []

    monkeypatch.setattr(
        "application.engine.services.memory_engine.time.monotonic",
        lambda: now,
    )

    def load_state(novel_id: str) -> MemoryState:
        calls.append(novel_id)
        return MemoryState(novel_id=novel_id, last_updated_chapter=len(calls))

    monkeypatch.setattr(engine, "_load_from_db", load_state)

    first = engine._get_or_load_state("n1")
    now = 10.5
    second = engine._get_or_load_state("n1")
    now = 11.1
    third = engine._get_or_load_state("n1")

    assert first is second
    assert third is not first
    assert third.last_updated_chapter == 2
    assert calls == ["n1", "n1"]


def test_memory_engine_state_cache_can_be_disabled(monkeypatch):
    engine = _engine(ttl=0.0, max_size=2)
    calls = []

    def load_state(novel_id: str) -> MemoryState:
        calls.append(novel_id)
        return MemoryState(novel_id=novel_id)

    monkeypatch.setattr(engine, "_load_from_db", load_state)

    engine._get_or_load_state("n1")
    engine._get_or_load_state("n1")

    assert calls == ["n1", "n1"]
    assert engine._cache == {}
    assert engine._cache_loaded_at == {}
