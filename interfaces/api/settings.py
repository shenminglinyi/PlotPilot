"""Backend settings and process-level environment bootstrap."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from infrastructure.ai.embedding_environment import EmbeddingEnvironmentSettings
from infrastructure.ai.llm_environment import LLMEnvironmentSettings
from infrastructure.ai.process_environment import (
    configure_huggingface_process_environment,
)
from infrastructure.ai.vector_store_environment import VectorStoreEnvironmentSettings


APP_RELEASE_VERSION = "1.0.2"
BACKEND_BUILD_ID = "build-20260209-1200-c4d2"
API_V1_PREFIX = "/api/v1"
NOVELS_API_PREFIX = f"{API_V1_PREFIX}/novels"
STATS_API_PREFIX = "/api/stats"


def configure_process_environment() -> None:
    """Apply process environment defaults required before heavy imports."""
    configure_huggingface_process_environment()


def _split_csv_env(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or ["*"]


@dataclass(frozen=True)
class EmbeddingSettings:
    """Environment fallback for embedding configuration.

    Runtime database configuration still has priority; these values preserve the
    existing env fallback behavior when the database is unavailable.
    """

    service: str = "local"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    model_path: str = ""
    use_gpu: bool = True

    @classmethod
    def from_env(cls) -> "EmbeddingSettings":
        env = EmbeddingEnvironmentSettings.from_env()
        return cls(
            service=env.service,
            api_key=env.api_key,
            base_url=env.base_url,
            model=env.model,
            model_path=env.model_path,
            use_gpu=env.use_gpu,
        )


@dataclass(frozen=True)
class VectorStoreSettings:
    """Typed view of vector store environment variables."""

    enabled: bool = True
    store_type: str = ""
    persist_directory: str = "./data/chromadb"
    legacy_qdrant_enabled: bool = False
    qdrant_host: str = "localhost"
    qdrant_port: str = "6333"
    qdrant_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "VectorStoreSettings":
        env = VectorStoreEnvironmentSettings.from_env()
        return cls(
            enabled=env.enabled,
            store_type=env.store_type,
            persist_directory=env.persist_directory,
            legacy_qdrant_enabled=env.legacy_qdrant_enabled,
            qdrant_host=env.qdrant_host,
            qdrant_port=env.qdrant_port,
            qdrant_api_key=env.qdrant_api_key,
        )

    @property
    def use_qdrant(self) -> bool:
        return self.store_type == "qdrant" or self.legacy_qdrant_enabled


@dataclass(frozen=True)
class BackendSettings:
    """Typed view over existing backend environment variables.

    This deliberately preserves all current variable names and defaults.
    """

    release_version: str = APP_RELEASE_VERSION
    build_id: str = BACKEND_BUILD_ID
    api_v1_prefix: str = API_V1_PREFIX
    novels_api_prefix: str = NOVELS_API_PREFIX
    stats_api_prefix: str = STATS_API_PREFIX
    log_level: str = "INFO"
    log_file: str = "logs/plotpilot.log"
    cors_origins: tuple[str, ...] = ("*",)
    disable_auto_daemon: bool = False
    frontend_dir: Path = Path("frontend/dist")
    llm: LLMEnvironmentSettings = field(default_factory=LLMEnvironmentSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)
    vector_store: VectorStoreSettings = field(default_factory=VectorStoreSettings)

    @classmethod
    def from_env(cls, root: Path | None = None) -> "BackendSettings":
        project_root = root or Path(__file__).resolve().parents[2]
        cors_origins = tuple(_split_csv_env(os.getenv("CORS_ORIGINS", "")))
        disable_auto_daemon = os.getenv("DISABLE_AUTO_DAEMON", "").lower() in (
            "1",
            "true",
            "yes",
        )
        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE", "logs/plotpilot.log"),
            cors_origins=cors_origins,
            disable_auto_daemon=disable_auto_daemon,
            frontend_dir=project_root / "frontend" / "dist",
            llm=LLMEnvironmentSettings.from_env(),
            embedding=EmbeddingSettings.from_env(),
            vector_store=VectorStoreSettings.from_env(),
        )


def get_backend_settings() -> BackendSettings:
    return BackendSettings.from_env()
