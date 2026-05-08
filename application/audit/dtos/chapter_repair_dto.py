"""章节修复扫描结果 DTO"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShortChapterDTO:
    """短章节扫描结果项"""
    chapter_number: int
    title: str
    word_count: int
    status: str
    content_preview: str  # 前 200 字
    severity: str  # "critical"(<1000) / "warning"(<2500) / "info"(<threshold)


@dataclass
class ChapterRepairScanResult:
    """短章节扫描结果"""
    novel_id: str
    threshold: int
    total_chapters: int
    short_chapters: list[ShortChapterDTO] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)  # {"critical": N, "warning": N, "info": N}
