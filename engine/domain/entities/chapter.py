"""Chapter实体 — 章节模型

核心职责：
- 管理段落(Paragraph)列表
- 维护张力三维度(plot/emotional/pacing)
- 支持质量评分
- 支持大纲(outline)和内容(content)分离
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class ChapterStatus(str, Enum):
    """章节状态"""
    DRAFT = "draft"
    REVIEWING = "reviewing"
    COMPLETED = "completed"


@dataclass
class Paragraph:
    """段落 — 章节的基本组成单元"""
    content: str
    position: int = 0
    paragraph_type: str = "narrative"  # narrative/dialogue/action/description
    advances_goal: Optional[str] = None  # 推进了哪个目标

    @property
    def word_count(self) -> int:
        """中文词数估算"""
        if not self.content:
            return 0
        # 去除空白字符后计算
        clean = self.content.replace(" ", "").replace("\n", "").replace("\t", "")
        return len(clean)


@dataclass
class ChapterQualityScore:
    """章节质量评分 — 由QualityGuardrail计算"""
    language_style: float = 0.0       # 语言风格 0-1
    character_consistency: float = 0.0 # 角色一致性 0-1
    plot_density: float = 0.0          # 情节密度 0-1
    rhythm: float = 0.0                # 节奏 0-1
    overall: float = 0.0               # 综合评分 0-1
    violations: List[str] = field(default_factory=list)

    @property
    def is_passing(self) -> bool:
        """是否通过质量检查"""
        return self.overall >= 0.6 and len(self.violations) == 0


@dataclass
class Chapter:
    """章节实体

    核心设计：
    - paragraphs：段落列表，每个段落可独立检查
    - tension三维度：plot/emotional/pacing
    - quality_score：质量守门人评分
    - outline与content分离：先规划后执行
    """
    chapter_number: int
    title: str = ""
    outline: str = ""
    content: str = ""
    paragraphs: List[Paragraph] = field(default_factory=list)
    status: ChapterStatus = ChapterStatus.DRAFT

    # 张力三维度
    plot_tension: float = 50.0       # 情节张力 0-100
    emotional_tension: float = 50.0  # 情绪张力 0-100
    pacing_tension: float = 50.0     # 节奏张力 0-100
    tension_score: float = 50.0      # 综合张力 0-100

    # 质量评分
    quality_score: Optional[ChapterQualityScore] = None

    # 章节目标
    chapter_goal: str = ""
    chapter_hook: str = ""  # 章末钩子类型

    @property
    def word_count(self) -> int:
        """总字数"""
        if self.content:
            clean = self.content.replace(" ", "").replace("\n", "").replace("\t", "")
            return len(clean)
        return sum(p.word_count for p in self.paragraphs)

    def add_paragraph(self, paragraph: Paragraph) -> None:
        """添加段落"""
        paragraph.position = len(self.paragraphs)
        self.paragraphs.append(paragraph)

    def update_content_from_paragraphs(self) -> None:
        """从段落列表更新content"""
        self.content = "\n\n".join(p.content for p in sorted(self.paragraphs, key=lambda p: p.position))

    def update_tension(self, plot: float = None, emotional: float = None, pacing: float = None) -> None:
        """更新张力维度"""
        if plot is not None:
            self.plot_tension = max(0, min(100, plot))
        if emotional is not None:
            self.emotional_tension = max(0, min(100, emotional))
        if pacing is not None:
            self.pacing_tension = max(0, min(100, pacing))
        # 综合张力 = 加权平均
        self.tension_score = (
            self.plot_tension * 0.4 +
            self.emotional_tension * 0.35 +
            self.pacing_tension * 0.15 +
            min(self.plot_tension, self.emotional_tension, self.pacing_tension) * 0.1
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化"""
        return {
            "chapter_number": self.chapter_number,
            "title": self.title,
            "status": self.status.value,
            "word_count": self.word_count,
            "tension_score": self.tension_score,
            "quality_score": self.quality_score.overall if self.quality_score else None,
            "paragraph_count": len(self.paragraphs),
        }
