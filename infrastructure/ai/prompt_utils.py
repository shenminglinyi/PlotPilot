"""prompt_utils — CPMS prompt fetch utility functions."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)


class PromptTemplateUnavailable(RuntimeError):
    """Required CPMS prompt node is missing, unavailable, or incomplete."""


def get_optional_prompt_system(node_key: str) -> str:
    """Get a system prompt for optional, non-generative helpers.

    Missing CPMS returns an empty string. Runtime LLM generation paths should use
    ``get_required_prompt_system`` or ``render_required_prompt`` instead.
    """
    try:
        from infrastructure.ai.prompt_registry import get_prompt_registry
        registry = get_prompt_registry()
        system = registry.get_system(node_key)
        if system:
            return system
    except Exception as exc:
        logger.debug("PromptRegistry unavailable (node_key=%s): %s", node_key, exc)

    return ""


def get_required_prompt_system(node_key: str) -> str:
    """Get a system prompt from CPMS and fail fast when it is unavailable.

    Use this for runtime LLM paths where hidden hardcoded prompt fallback would
    pollute generated state. Optional/non-LLM degraded behavior should be handled
    by the caller explicitly after this function fails; do not pass fallback text.
    """
    try:
        from infrastructure.ai.prompt_registry import get_prompt_registry

        system = get_prompt_registry().get_system(node_key)
    except Exception as exc:
        raise PromptTemplateUnavailable(
            f"CPMS PromptRegistry 不可用，已阻塞提示词读取: {node_key}"
        ) from exc

    if not system or not system.strip():
        raise PromptTemplateUnavailable(
            f"CPMS prompt node system unavailable or empty: {node_key}"
        )
    return system.strip()


def get_optional_prompt_user_template(node_key: str) -> str:
    """Get a user template for optional, non-generative helpers."""
    try:
        from infrastructure.ai.prompt_registry import get_prompt_registry
        registry = get_prompt_registry()
        user_template = registry.get_user_template(node_key)
        if user_template:
            return user_template
    except Exception as exc:
        logger.debug("PromptRegistry unavailable (node_key=%s): %s", node_key, exc)

    return ""


def render_required_prompt(node_key: str, variables: Optional[Dict[str, Any]] = None) -> Prompt:
    """Render a complete Prompt from CPMS and fail fast when unavailable."""
    try:
        from infrastructure.ai.prompt_registry import get_prompt_registry

        prompt = get_prompt_registry().render_to_prompt(node_key, variables or {})
    except Exception as exc:
        raise PromptTemplateUnavailable(
            f"CPMS PromptRegistry 不可用，已阻塞提示词渲染: {node_key}"
        ) from exc

    if not prompt or not prompt.system.strip() or not prompt.user.strip():
        raise PromptTemplateUnavailable(
            f"CPMS prompt node unavailable or incomplete: {node_key}"
        )
    return prompt
