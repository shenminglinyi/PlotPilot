from infrastructure.ai.embedding_environment import EmbeddingEnvironmentSettings


def test_embedding_environment_defaults(monkeypatch):
    for name in (
        "EMBEDDING_SERVICE",
        "EMBEDDING_API_KEY",
        "OPENAI_API_KEY",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_MODEL_PATH",
        "LOCAL_EMBEDDING_MODEL_PATH",
        "EMBEDDING_USE_GPU",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = EmbeddingEnvironmentSettings.from_env()

    assert settings.service == "local"
    assert settings.api_key_with_openai_fallback == ""
    assert settings.model == ""
    assert settings.model_path == ""
    assert settings.db_default_model_path == ""
    assert settings.use_gpu is True


def test_embedding_environment_overrides_and_fallbacks(monkeypatch):
    monkeypatch.setenv("EMBEDDING_SERVICE", "OpenAI")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embeddings.example")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", "/models/current")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL_PATH", "/models/legacy")
    monkeypatch.setenv("EMBEDDING_USE_GPU", "false")

    settings = EmbeddingEnvironmentSettings.from_env()

    assert settings.service == "openai"
    assert settings.api_key_with_openai_fallback == "openai-key"
    assert settings.base_url == "https://embeddings.example"
    assert settings.model == "embedding-model"
    assert settings.model_path == "/models/current"
    assert settings.db_default_model_path == "/models/legacy"
    assert settings.use_gpu is False


def test_embedding_environment_embedding_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    settings = EmbeddingEnvironmentSettings.from_env()

    assert settings.api_key_with_openai_fallback == "embedding-key"
