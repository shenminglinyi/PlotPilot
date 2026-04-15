"""Compatibility wrapper for legacy statistics model imports."""

from interfaces.api.stats.models.stats_models import (
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

