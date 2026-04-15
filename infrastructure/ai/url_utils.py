from __future__ import annotations

from typing import Optional


def _strip_known_suffix(url: str, suffixes: tuple[str, ...]) -> str:
    normalized = (url or '').strip().rstrip('/')
    lower = normalized.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            return normalized[: -len(suffix)].rstrip('/')
    return normalized


def normalize_openai_base_url(url: Optional[str]) -> Optional[str]:
    if not url or not str(url).strip():
        return None
    return _strip_known_suffix(
        str(url),
        (
            '/chat/completions',
            '/v1/chat/completions',
            '/completions',
        ),
    )


def normalize_anthropic_base_url(url: Optional[str]) -> Optional[str]:
    if not url or not str(url).strip():
        return None
    return _strip_known_suffix(
        str(url),
        (
            '/v1/messages',
            '/messages',
        ),
    )


def normalize_gemini_base_url(url: Optional[str]) -> Optional[str]:
    if not url or not str(url).strip():
        return None
    return _strip_known_suffix(
        str(url),
        (
            '/models',
            '/v1beta/models',
            '/v1/models',
        ),
    )
