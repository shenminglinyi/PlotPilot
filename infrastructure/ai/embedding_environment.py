"""Environment-backed embedding configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_text(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


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
        )

    @property
    def api_key_with_openai_fallback(self) -> str:
        return self.api_key or self.openai_api_key

    @property
    def db_default_model_path(self) -> str:
        return self.legacy_local_model_path
