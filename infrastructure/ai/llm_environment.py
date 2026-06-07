"""Environment-backed LLM provider configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass


ARK_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def _env_text(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


@dataclass(frozen=True)
class LLMEnvironmentSettings:
    """Typed view of legacy LLM-related environment variables."""

    provider: str = ""
    writing_model: str = ""
    system_model: str = ""
    anthropic_api_key: str = ""
    anthropic_auth_token: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""
    gemini_api_key: str = ""
    gemini_base_url: str = ""
    gemini_model: str = ""
    ark_api_key: str = ""
    ark_base_url: str = ""
    ark_model: str = ""

    @classmethod
    def from_env(cls) -> "LLMEnvironmentSettings":
        return cls(
            provider=_env_text("LLM_PROVIDER").lower(),
            writing_model=_env_text("WRITING_MODEL"),
            system_model=_env_text("SYSTEM_MODEL"),
            anthropic_api_key=_env_text("ANTHROPIC_API_KEY"),
            anthropic_auth_token=_env_text("ANTHROPIC_AUTH_TOKEN"),
            anthropic_base_url=_env_text("ANTHROPIC_BASE_URL"),
            anthropic_model=_env_text("ANTHROPIC_MODEL"),
            openai_api_key=_env_text("OPENAI_API_KEY"),
            openai_base_url=_env_text("OPENAI_BASE_URL"),
            openai_model=_env_text("OPENAI_MODEL"),
            gemini_api_key=_env_text("GEMINI_API_KEY"),
            gemini_base_url=_env_text("GEMINI_BASE_URL"),
            gemini_model=_env_text("GEMINI_MODEL"),
            ark_api_key=_env_text("ARK_API_KEY"),
            ark_base_url=_env_text("ARK_BASE_URL"),
            ark_model=_env_text("ARK_MODEL"),
        )

    @property
    def anthropic_api_key_with_token_fallback(self) -> str:
        return self.anthropic_api_key or self.anthropic_auth_token

    @property
    def openai_preset_key(self) -> str:
        if self.openai_base_url:
            return "custom-openai-compatible"
        return "openai-official"

    @property
    def ark_base_url_or_default(self) -> str:
        return self.ark_base_url or ARK_DEFAULT_BASE_URL
