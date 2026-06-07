"""API URL builders for response payloads and internal references."""
from __future__ import annotations

from interfaces.api.settings import API_V1_PREFIX


def bible_generation_status_url(novel_id: str) -> str:
    return f"{API_V1_PREFIX}/bible/novels/{novel_id}/bible/status"
