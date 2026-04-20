"""E2E test fixtures: full app stack with in-memory DB."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infrastructure.persistence.database.connection import DatabaseConnection

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "infrastructure" / "persistence" / "database" / "schema.sql"


@pytest.fixture
def db():
    """In-memory database for e2e tests."""
    db = DatabaseConnection(":memory:")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    db.get_connection().executescript(schema_sql)
    db.get_connection().commit()
    yield db
    db.close()


@pytest.fixture
def client(db, monkeypatch):
    """FastAPI test client with mocked database, suitable for CI."""

    def mock_get_database():
        return db

    monkeypatch.setattr(
        "infrastructure.persistence.database.connection.get_database",
        mock_get_database,
    )
    monkeypatch.setattr(
        "interfaces.api.dependencies.get_database",
        mock_get_database,
    )

    from interfaces.main import app

    return TestClient(app)
