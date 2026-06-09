"""Environment-backed embedding configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from infrastructure.ai.http_timeout import DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS, HttpTimeoutSettings


def _env_text(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


def _env_positive_float(name: str, default: float) -> float:
    try:
        value = float(_env_text(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class EmbeddingEnvironmentSettings:
    """Typed view of legacy embedding environment variables."""

    service: str = "local"
    api_key: str = ""
    openai_api_key: str = ""
    base_url: str = ""
    model: str = ""
    model_path: str = ""
    legacy_local_model_path: str = ""
    use_gpu: bool = True
    timeout_seconds: float = DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.timeout_seconds
    connect_timeout: float = DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.connect_timeout
    read_timeout: float = DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.read_timeout
    write_timeout: float = DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.write_timeout
    pool_timeout: float = DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.pool_timeout

    @classmethod
    def from_env(cls) -> "EmbeddingEnvironmentSettings":
        return cls(
            service=_env_text("EMBEDDING_SERVICE", "local").lower(),
            api_key=_env_text("EMBEDDING_API_KEY"),
            openai_api_key=_env_text("OPENAI_API_KEY"),
            base_url=_env_text("EMBEDDING_BASE_URL"),
            model=_env_text("EMBEDDING_MODEL"),
            model_path=_env_text("EMBEDDING_MODEL_PATH"),
            legacy_local_model_path=_env_text("LOCAL_EMBEDDING_MODEL_PATH"),
            use_gpu=_env_text("EMBEDDING_USE_GPU", "true").lower() == "true",
            timeout_seconds=_env_positive_float(
                "EMBEDDING_TIMEOUT_SECONDS",
                DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.timeout_seconds,
            ),
            connect_timeout=_env_positive_float(
                "EMBEDDING_CONNECT_TIMEOUT_SECONDS",
                DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.connect_timeout,
            ),
            read_timeout=_env_positive_float(
                "EMBEDDING_READ_TIMEOUT_SECONDS",
                DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.read_timeout,
            ),
            write_timeout=_env_positive_float(
                "EMBEDDING_WRITE_TIMEOUT_SECONDS",
                DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.write_timeout,
            ),
            pool_timeout=_env_positive_float(
                "EMBEDDING_POOL_TIMEOUT_SECONDS",
                DEFAULT_EMBEDDING_HTTP_TIMEOUT_SETTINGS.pool_timeout,
            ),
        )

    @property
    def api_key_with_openai_fallback(self) -> str:
        return self.api_key or self.openai_api_key

    @property
    def db_default_model_path(self) -> str:
        return self.legacy_local_model_path

    @property
    def http_timeout_settings(self) -> HttpTimeoutSettings:
        return HttpTimeoutSettings(
            timeout_seconds=self.timeout_seconds,
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            write_timeout=self.write_timeout,
            pool_timeout=self.pool_timeout,
        )
