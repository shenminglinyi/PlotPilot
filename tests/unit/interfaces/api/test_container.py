from unittest.mock import MagicMock, patch

from interfaces.api.container import AppContainer


def test_container_caches_llm_runtime_services():
    container = AppContainer()

    with patch("interfaces.api.container.LLMControlService") as control_cls:
        control = MagicMock()
        control_cls.return_value = control

        assert container.get_llm_control_service() is control
        assert container.get_llm_control_service() is control
        control_cls.assert_called_once()


def test_container_vector_store_reset(monkeypatch):
    container = AppContainer()
    monkeypatch.delenv("VECTOR_STORE_TYPE", raising=False)
    monkeypatch.delenv("QDRANT_ENABLED", raising=False)

    with patch("infrastructure.ai.chromadb_vector_store.ChromaDBVectorStore") as cls:
        first = MagicMock()
        second = MagicMock()
        cls.side_effect = [first, second]

        assert container.get_vector_store() is first
        assert container.get_vector_store() is first
        container.reset_vector_store()
        assert container.get_vector_store() is second

    assert cls.call_count == 2
