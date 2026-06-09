"""LLM retry policy shared by provider and structured-output pipelines.

The limits here intentionally stay small: callers may retry transient transport
or empty-response failures, but no path should loop indefinitely or spend user
tokens without a bounded budget.
"""

# 含首次调用在内，同一结构化/解析流程最多调用 LLM 的次数
LLM_MAX_TOTAL_ATTEMPTS = 3

_RETRYABLE_MARKERS = (
    "api returned empty content",
    "returned empty content",
    "empty non-stream content",
    "empty content",
    "empty response",
    "overloaded_error",
    "rate limit",
    "timeout",
    "temporar",
    "connection reset",
    "connection error",
    "service unavailable",
)

_RETRYABLE_STATUSES = (" 408", " 409", " 425", " 429", " 500", " 502", " 503", " 504", " 529")


def is_retryable_llm_error(exc: Exception | str) -> bool:
    """Return True for transient LLM/provider failures worth retrying.

    This deliberately includes empty upstream content. Several OpenAI-compatible
    gateways occasionally return a syntactically successful response with no
    text; treating that as retryable keeps module-specific callers from each
    inventing their own empty-response handling.
    """
    message = str(exc).lower()
    return any(marker in message for marker in _RETRYABLE_MARKERS) or any(
        status in message for status in _RETRYABLE_STATUSES
    )
