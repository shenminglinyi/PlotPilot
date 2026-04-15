"""Compatibility wrapper for the historic ``aitext.web.models.stats_models`` path."""

from web.models.stats_models import (
    BookStats,
    ChapterStats,
    ContentAnalysis,
    GlobalStats,
    WritingProgress,
)

__all__ = [
    "BookStats",
    "ChapterStats",
    "ContentAnalysis",
    "GlobalStats",
    "WritingProgress",
]
