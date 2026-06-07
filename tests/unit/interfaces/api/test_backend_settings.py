from pathlib import Path

from interfaces.api.settings import (
    API_V1_PREFIX,
    BackendSettings,
    configure_process_environment,
)


def test_backend_settings_defaults(monkeypatch, tmp_path):
    for name in (
        "LOG_LEVEL",
        "LOG_FILE",
        "CORS_ORIGINS",
        "DISABLE_AUTO_DAEMON",
        "VECTOR_STORE_ENABLED",
        "VECTOR_STORE_TYPE",
        "VECTOR_STORE_PATH",
        "QDRANT_ENABLED",
        "QDRANT_HOST",
        "QDRANT_PORT",
        "QDRANT_API_KEY",
        "EMBEDDING_SERVICE",
        "EMBEDDING_API_KEY",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_MODEL_PATH",
        "EMBEDDING_USE_GPU",
        "LLM_PROVIDER",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = BackendSettings.from_env(root=tmp_path)

    assert settings.api_v1_prefix == API_V1_PREFIX
    assert settings.log_level == "INFO"
    assert settings.log_file == "logs/plotpilot.log"
    assert settings.cors_origins == ("*",)
    assert settings.disable_auto_daemon is False
    assert settings.frontend_dir == tmp_path / "frontend" / "dist"
    assert settings.vector_store.enabled is True
    assert settings.vector_store.store_type == ""
    assert settings.vector_store.persist_directory == "./data/chromadb"
    assert settings.vector_store.qdrant_host == "localhost"
    assert settings.vector_store.qdrant_port == "6333"
    assert settings.embedding.service == "local"
    assert settings.embedding.use_gpu is True
    assert settings.llm.provider == ""


def test_backend_settings_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FILE", "logs/custom.log")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://app.example")
    monkeypatch.setenv("DISABLE_AUTO_DAEMON", "yes")
    monkeypatch.setenv("VECTOR_STORE_ENABLED", "false")
    monkeypatch.setenv("VECTOR_STORE_TYPE", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_PATH", "/tmp/chromadb")
    monkeypatch.setenv("QDRANT_ENABLED", "true")
    monkeypatch.setenv("QDRANT_HOST", "qdrant.example.com")
    monkeypatch.setenv("QDRANT_PORT", "7333")
    monkeypatch.setenv("QDRANT_API_KEY", "qdrant-key")
    monkeypatch.setenv("EMBEDDING_SERVICE", "openai")
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embeddings.example")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-test")
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", "/models/embed")
    monkeypatch.setenv("EMBEDDING_USE_GPU", "false")
    monkeypatch.setenv("LLM_PROVIDER", "OpenAI")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("WRITING_MODEL", "writing-model")

    settings = BackendSettings.from_env(root=tmp_path)

    assert settings.log_level == "DEBUG"
    assert settings.log_file == "logs/custom.log"
    assert settings.cors_origins == ("http://localhost:5173", "https://app.example")
    assert settings.disable_auto_daemon is True
    assert settings.vector_store.enabled is False
    assert settings.vector_store.use_qdrant is True
    assert settings.vector_store.persist_directory == "/tmp/chromadb"
    assert settings.vector_store.qdrant_host == "qdrant.example.com"
    assert settings.vector_store.qdrant_port == "7333"
    assert settings.vector_store.qdrant_api_key == "qdrant-key"
    assert settings.embedding.service == "openai"
    assert settings.embedding.api_key == "embedding-key"
    assert settings.embedding.base_url == "https://embeddings.example"
    assert settings.embedding.model == "text-embedding-test"
    assert settings.embedding.model_path == "/models/embed"
    assert settings.embedding.use_gpu is False
    assert settings.llm.provider == "openai"
    assert settings.llm.openai_api_key == "openai-key"
    assert settings.llm.writing_model == "writing-model"


def test_configure_process_environment_preserves_required_offline_flags(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.delenv("HF_DATASETS_OFFLINE", raising=False)
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "true")

    configure_process_environment()

    assert Path(".") is not None
    assert __import__("os").environ["HF_HUB_OFFLINE"] == "1"
    assert __import__("os").environ["TRANSFORMERS_OFFLINE"] == "1"
    assert __import__("os").environ["HF_DATASETS_OFFLINE"] == "1"
    assert __import__("os").environ["CURL_CA_BUNDLE"] == ""
    assert __import__("os").environ["REQUESTS_CA_BUNDLE"] == ""
