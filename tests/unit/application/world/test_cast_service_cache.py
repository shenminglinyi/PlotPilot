from pathlib import Path

from application.world.dtos.cast_dto import CastGraphDTO
from application.world.services.cast_runtime_settings import CastRuntimeSettings
from application.world.services.cast_service import CastService


def _service(tmp_path: Path, *, ttl: float = 100.0, max_size: int = 2) -> CastService:
    return CastService(
        tmp_path,
        runtime_settings=CastRuntimeSettings(
            graph_cache_ttl_seconds=ttl,
            graph_cache_max_size=max_size,
        ),
    )


def test_cast_graph_cache_reuses_recent_empty_graph(monkeypatch, tmp_path):
    service = _service(tmp_path)
    calls = []

    def load_facts(novel_id: str):
        calls.append(novel_id)
        return []

    monkeypatch.setattr(service, "_load_facts_list", load_facts)

    first = service.get_cast_graph("n1")
    second = service.get_cast_graph("n1")

    assert isinstance(first, CastGraphDTO)
    assert first is second
    assert calls == ["n1"]


def test_cast_graph_cache_evicts_oldest_entry_when_capacity_is_exceeded(monkeypatch, tmp_path):
    service = _service(tmp_path, max_size=2)
    calls = []

    def load_facts(novel_id: str):
        calls.append(novel_id)
        return []

    monkeypatch.setattr(service, "_load_facts_list", load_facts)

    service.get_cast_graph("n1")
    service.get_cast_graph("n2")
    service.get_cast_graph("n3")

    assert calls == ["n1", "n2", "n3"]
    assert set(service._graph_cache_ttl) == {"n2", "n3"}


def test_cast_graph_cache_can_be_disabled(monkeypatch, tmp_path):
    service = _service(tmp_path, ttl=0.0, max_size=2)
    calls = []

    def load_facts(novel_id: str):
        calls.append(novel_id)
        return []

    monkeypatch.setattr(service, "_load_facts_list", load_facts)

    service.get_cast_graph("n1")
    service.get_cast_graph("n1")

    assert calls == ["n1", "n1"]
    assert service._graph_cache_ttl == {}
