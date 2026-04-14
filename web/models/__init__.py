"""Compatibility exports for legacy web models."""

from .responses import ErrorResponse, PaginatedResponse, SuccessResponse
from .stats_models import BookStats, ChapterStats, ContentAnalysis, GlobalStats, WritingProgress

__all__ = [
    "BookStats",
    "ChapterStats",
    "ContentAnalysis",
    "ErrorResponse",
    "GlobalStats",
    "PaginatedResponse",
    "SuccessResponse",
    "WritingProgress",
]

