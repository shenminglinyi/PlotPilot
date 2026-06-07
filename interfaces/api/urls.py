"""API URL builders for response payloads, logging, and internal references."""
from __future__ import annotations

from interfaces.api.settings import API_V1_PREFIX, STATS_API_PREFIX


def bible_generation_status_url(novel_id: str) -> str:
    return f"{API_V1_PREFIX}/bible/novels/{novel_id}/bible/status"


def stats_api_url(path: str) -> str:
    """Build a stable stats API URL from a route-local path."""
    if not path:
        return STATS_API_PREFIX
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{STATS_API_PREFIX}{suffix}"
