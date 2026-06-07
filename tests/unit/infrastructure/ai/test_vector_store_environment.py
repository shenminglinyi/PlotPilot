from infrastructure.ai.vector_store_environment import VectorStoreEnvironmentSettings


def test_vector_store_environment_defaults(monkeypatch):
    for name in (
        "VECTOR_STORE_ENABLED",
        "VECTOR_STORE_TYPE",
        "VECTOR_STORE_PATH",
        "QDRANT_ENABLED",
        "QDRANT_HOST",
        "QDRANT_PORT",
        "QDRANT_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = VectorStoreEnvironmentSettings.from_env()

    assert settings.enabled is True
    assert settings.store_type == ""
    assert settings.persist_directory == "./data/chromadb"
    assert settings.use_qdrant is False
    assert settings.qdrant_host == "localhost"
    assert settings.qdrant_port == "6333"
    assert settings.qdrant_api_key is None


def test_vector_store_environment_qdrant_overrides(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_ENABLED", "false")
    monkeypatch.setenv("VECTOR_STORE_TYPE", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_PATH", "/tmp/chromadb")
    monkeypatch.setenv("QDRANT_HOST", "qdrant.example.com")
    monkeypatch.setenv("QDRANT_PORT", "7333")
    monkeypatch.setenv("QDRANT_API_KEY", "qdrant-key")

    settings = VectorStoreEnvironmentSettings.from_env()

    assert settings.enabled is False
    assert settings.use_qdrant is True
    assert settings.persist_directory == "/tmp/chromadb"
    assert settings.qdrant_host == "qdrant.example.com"
    assert settings.qdrant_port == "7333"
    assert settings.qdrant_api_key == "qdrant-key"


def test_vector_store_environment_legacy_qdrant_flag(monkeypatch):
    monkeypatch.delenv("VECTOR_STORE_TYPE", raising=False)
    monkeypatch.setenv("QDRANT_ENABLED", "true")

    settings = VectorStoreEnvironmentSettings.from_env()

    assert settings.legacy_qdrant_enabled is True
    assert settings.use_qdrant is True
