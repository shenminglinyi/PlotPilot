from infrastructure.ai.llm_environment import (
    ARK_DEFAULT_BASE_URL,
    LLMEnvironmentSettings,
)


LLM_ENV_NAMES = (
    "LLM_PROVIDER",
    "WRITING_MODEL",
    "SYSTEM_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_BASE_URL",
    "GEMINI_MODEL",
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "ARK_MODEL",
)


def _clear_llm_env(monkeypatch):
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_llm_environment_defaults(monkeypatch):
    _clear_llm_env(monkeypatch)

    settings = LLMEnvironmentSettings.from_env()

    assert settings.provider == ""
    assert settings.anthropic_api_key_with_token_fallback == ""
    assert settings.openai_preset_key == "openai-official"
    assert settings.ark_base_url_or_default == ARK_DEFAULT_BASE_URL


def test_llm_environment_lowercases_provider_and_preserves_models(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "OpenAI")
    monkeypatch.setenv("WRITING_MODEL", "writing-model")
    monkeypatch.setenv("SYSTEM_MODEL", "system-model")

    settings = LLMEnvironmentSettings.from_env()

    assert settings.provider == "openai"
    assert settings.writing_model == "writing-model"
    assert settings.system_model == "system-model"


def test_llm_environment_anthropic_token_fallback(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-key")

    settings = LLMEnvironmentSettings.from_env()

    assert settings.anthropic_api_key_with_token_fallback == "token-key"


def test_llm_environment_anthropic_api_key_takes_precedence(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "api-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-key")

    settings = LLMEnvironmentSettings.from_env()

    assert settings.anthropic_api_key_with_token_fallback == "api-key"


def test_llm_environment_openai_base_url_selects_custom_preset(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")

    settings = LLMEnvironmentSettings.from_env()

    assert settings.openai_base_url == "https://gateway.example/v1"
    assert settings.openai_preset_key == "custom-openai-compatible"


def test_llm_environment_ark_base_url_default_and_override(monkeypatch):
    _clear_llm_env(monkeypatch)
    assert LLMEnvironmentSettings.from_env().ark_base_url_or_default == ARK_DEFAULT_BASE_URL

    monkeypatch.setenv("ARK_BASE_URL", "https://ark.example/api/v3")
    assert LLMEnvironmentSettings.from_env().ark_base_url_or_default == "https://ark.example/api/v3"
