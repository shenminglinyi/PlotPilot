"""Environment-backed vector store configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_text(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


@dataclass(frozen=True)
class VectorStoreEnvironmentSettings:
    """Typed view of legacy vector store environment variables."""

    enabled: bool = True
    store_type: str = ""
    persist_directory: str = "./data/chromadb"
    legacy_qdrant_enabled: bool = False
    qdrant_host: str = "localhost"
    qdrant_port: str = "6333"
    qdrant_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "VectorStoreEnvironmentSettings":
        return cls(
            enabled=_env_text("VECTOR_STORE_ENABLED", "true").lower() == "true",
            store_type=_env_text("VECTOR_STORE_TYPE").lower(),
            persist_directory=os.getenv("VECTOR_STORE_PATH", "./data/chromadb"),
            legacy_qdrant_enabled=_env_text("QDRANT_ENABLED").lower() == "true",
            qdrant_host=_env_text("QDRANT_HOST", "localhost") or "localhost",
            qdrant_port=os.getenv("QDRANT_PORT", "6333"),
            qdrant_api_key=_env_text("QDRANT_API_KEY") or None,
        )

    @property
    def use_qdrant(self) -> bool:
        return self.store_type == "qdrant" or self.legacy_qdrant_enabled
