from application.ai.embedding_config_service import EmbeddingConfigService


def test_embedding_config_default_row_uses_embedding_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "env-embedding-model")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL_PATH", "/legacy/local/model")
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", "/current/local/model")

    defaults = EmbeddingConfigService._default_row_values()

    assert defaults["model"] == "env-embedding-model"
    assert defaults["model_path"] == "/legacy/local/model"
    assert defaults["mode"] == "openai"
