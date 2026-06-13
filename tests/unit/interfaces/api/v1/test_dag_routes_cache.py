import pytest

from interfaces.api.v1.engine.dag import dag_routes
from interfaces.api.v1.engine.dag.dag_runtime_settings import DAGRuntimeSettings


@pytest.fixture(autouse=True)
def clear_dag_cache():
    dag_routes._dag_cache.clear()
    yield
    dag_routes._dag_cache.clear()


def test_dag_cache_evicts_least_recently_used_entry(monkeypatch):
    monkeypatch.setattr(
        dag_routes,
        "get_dag_runtime_settings",
        lambda: DAGRuntimeSettings(dag_cache_max_size=2),
    )

    first = dag_routes._get_dag_for_novel("n1")
    second = dag_routes._get_dag_for_novel("n2")
    assert dag_routes._get_dag_for_novel("n1") is first

    third = dag_routes._get_dag_for_novel("n3")

    assert set(dag_routes._dag_cache) == {"n1", "n3"}
    assert dag_routes._dag_cache["n1"] is first
    assert dag_routes._dag_cache["n3"] is third
    assert second not in dag_routes._dag_cache.values()


def test_dag_cache_reuses_cached_dag(monkeypatch):
    monkeypatch.setattr(
        dag_routes,
        "get_dag_runtime_settings",
        lambda: DAGRuntimeSettings(dag_cache_max_size=2),
    )

    first = dag_routes._get_dag_for_novel("n1")
    second = dag_routes._get_dag_for_novel("n1")

    assert first is second
    assert list(dag_routes._dag_cache) == ["n1"]
