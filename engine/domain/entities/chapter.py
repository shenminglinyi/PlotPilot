"""兼容层 — engine.domain.entities.chapter

⚠️ 已废弃，请使用: from engine.core.entities.chapter import ...
"""
from engine.core.entities.chapter import (
    Chapter, ChapterStatus, Paragraph, ChapterQualityScore,
)

__all__ = ["Chapter", "ChapterStatus", "Paragraph", "ChapterQualityScore"]
