from types import SimpleNamespace
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

import application.ai.embedding_config_service as embedding_config_module
from application.ai.embedding_config_service import (
    EmbeddingConfigModel,
    EmbeddingConfigService,
)
from infrastructure.persistence.database.connection import DatabaseConnection
from interfaces.api.v1.core.settings import embedding_router


def test_embedding_config_service_prefers_global_db(monkeypatch):
    fake_db = object()
    fake_dependencies = SimpleNamespace(get_db=lambda: fake_db)
    monkeypatch.setitem(sys.modules, "interfaces.api.dependencies", fake_dependencies)

    service = EmbeddingConfigService()

    assert service._get_db() is fake_db


def test_embedding_settings_endpoint_returns_config(monkeypatch):
    fake_payload = {
        "mode": "local",
        "api_key": "",
        "base_url": "",
        "model": "text-embedding-3-small",
        "use_gpu": True,
        "model_path": "./.models/bge-small-zh-v1.5",
        "created_at": "2026-04-16T00:00:00",
        "updated_at": "2026-04-16T00:00:00",
    }
    fake_service = SimpleNamespace(to_api_dict=lambda: fake_payload)
    monkeypatch.setattr(
        embedding_config_module,
        "get_embedding_config_service",
        lambda: fake_service,
    )

    app = FastAPI()
    app.include_router(embedding_router, prefix="/api/v1")
    client = TestClient(app)

    response = client.get("/api/v1/settings/embedding/")

    assert response.status_code == 200
    assert response.json()["model_path"] == "./.models/bge-small-zh-v1.5"


def test_embedding_settings_update_endpoint_returns_updated_config(monkeypatch):
    fake_service = SimpleNamespace(
        update_config=lambda **_: EmbeddingConfigModel(
            model_path="./.models/bge-small-zh-v1.5",
            use_gpu=True,
            updated_at="2026-04-16T00:00:00",
        )
    )
    monkeypatch.setattr(
        embedding_config_module,
        "get_embedding_config_service",
        lambda: fake_service,
    )

    app = FastAPI()
    app.include_router(embedding_router, prefix="/api/v1")
    client = TestClient(app)

    response = client.put(
        "/api/v1/settings/embedding/",
        json={
            "mode": "local",
            "api_key": "",
            "base_url": "",
            "model": "text-embedding-3-small",
            "use_gpu": True,
            "model_path": "./.models/bge-small-zh-v1.5",
        },
    )

    assert response.status_code == 200
    assert response.json()["model_path"] == "./.models/bge-small-zh-v1.5"


def test_embedding_config_service_persists_with_database_connection(tmp_path):
    db = DatabaseConnection(str(tmp_path / "embedding-config.db"))
    service = EmbeddingConfigService(db)

    initial = service.get_config()
    updated = service.update_config(
        model_path="./.models/bge-small-zh-v1.5",
        use_gpu=False,
        model="bge-small-local",
    )

    assert initial.mode == "local"
    assert updated.model_path == "./.models/bge-small-zh-v1.5"
    assert updated.use_gpu is False
    assert updated.model == "bge-small-local"
    assert service.get_config().model == "bge-small-local"


def test_embedding_config_service_uses_env_defaults_on_first_read(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_SERVICE", "local")
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", "./.models/bge-small-zh-v1.5")
    monkeypatch.setenv("EMBEDDING_USE_GPU", "true")

    db = DatabaseConnection(str(tmp_path / "embedding-config-env.db"))
    service = EmbeddingConfigService(db)

    cfg = service.get_config()

    assert cfg.mode == "local"
    assert cfg.model_path == "./.models/bge-small-zh-v1.5"
    assert cfg.use_gpu is True
