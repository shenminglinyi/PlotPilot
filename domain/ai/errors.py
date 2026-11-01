"""Domain-level AI errors.

Raised when the runtime tries to create an LLM provider without a usable
configuration. Production paths must fail loudly instead of silently
falling back to placeholder content.
"""
from __future__ import annotations


class LLMNotConfiguredError(RuntimeError):
    """No usable LLM profile (missing config / API key / model name).

    Callers should surface this to the user as an actionable error
    (e.g. HTTP 503 with the message), never swallow it and continue
    with mock content.
    """
