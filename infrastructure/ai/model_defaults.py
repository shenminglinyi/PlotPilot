"""Helpers for resolving runtime LLM model names from runtime settings and env."""
import os

from infrastructure.ai.runtime_settings import load_llm_settings


def get_openai_default_model() -> str:
    """Default model for OpenAI-compatible providers."""
    runtime = load_llm_settings()
    return runtime.get("model") or os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o"


def get_anthropic_default_model() -> str:
    """Default model for Anthropic providers."""
    runtime = load_llm_settings()
    return runtime.get("model") or os.getenv("ANTHROPIC_MODEL") or os.getenv("LLM_MODEL") or "claude-sonnet-4-6"


def get_default_model() -> str:
    """Provider-aware default model for generic runtime components."""
    provider = (load_llm_settings().get("api_format") or "").lower()
    if provider != "anthropic_messages":
        return get_openai_default_model()
    return get_anthropic_default_model()


def get_fast_model() -> str:
    """Fast-path model for lightweight analysis tasks."""
    runtime = load_llm_settings()
    return runtime.get("fast_model") or os.getenv("FAST_LLM_MODEL") or get_default_model()


def get_review_model() -> str:
    """Model used for review and audit tasks."""
    runtime = load_llm_settings()
    return runtime.get("review_model") or os.getenv("REVIEW_LLM_MODEL") or get_fast_model()


def get_scene_director_model() -> str:
    """Model used by scene director analysis."""
    runtime = load_llm_settings()
    return runtime.get("scene_director_model") or os.getenv("SCENE_DIRECTOR_MODEL") or get_fast_model()


def get_state_extractor_model() -> str:
    """Model used for chapter-state extraction."""
    runtime = load_llm_settings()
    return runtime.get("state_extractor_model") or os.getenv("STATE_EXTRACTOR_MODEL") or get_default_model()
