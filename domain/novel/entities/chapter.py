# domain/novel/entities/chapter.py
from enum import Enum
from datetime import datetime
from domain.shared.base_entity import BaseEntity
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_content import ChapterContent
from domain.novel.value_objects.word_count import WordCount


class ChapterStatus(str, Enum):
    """章节状态"""
    DRAFT = "draft"
    REVIEWING = "reviewing"
    COMPLETED = "completed"


class Chapter(BaseEntity):
    """章节实体"""

    def __init__(
        self,
        id: str,
        novel_id: NovelId,
        number: int,
        title: str,
        content: str = "",
        outline: str = "",
        status: ChapterStatus = ChapterStatus.DRAFT,
        tension_score: float = 50.0,
        plot_tension: float = 50.0,
        emotional_tension: float = 50.0,
        pacing_tension: float = 50.0,
    ):
        super().__init__(id)
        self.novel_id = novel_id
        self.number = number
        self.title = title
        self._content_text = content  # 直接存储文本，允许空内容
        self.outline = outline  # 章节大纲
        self.status = status
        self.tension_score = tension_score  # 章节综合张力值 0-100
        self.plot_tension = plot_tension  # 情节张力 0-100
        self.emotional_tension = emotional_tension  # 情绪张力 0-100
        self.pacing_tension = pacing_tension  # 节奏张力 0-100

    @property
    def content(self) -> str:
        return self._content_text

    @property
    def word_count(self) -> WordCount:
        if not self._content_text:
            return WordCount(0)
        content_obj = ChapterContent(self._content_text)
        return WordCount(content_obj.word_count())

    def update_content(self, content: str) -> None:
        """更新内容（允许空内容用于草稿）"""
        self._content_text = content
        self.updated_at = datetime.utcnow()

    def update_tension_score(self, score: float) -> None:
        """更新张力分数（0-100）"""
        if not 0 <= score <= 100:
            raise ValueError(f"Tension score must be between 0 and 100, got {score}")
        self.tension_score = score
        self.updated_at = datetime.utcnow()

    def update_tension_dimensions(self, dimensions: "TensionDimensions") -> None:
        """从 TensionDimensions 值对象更新全部张力字段。"""
        self.plot_tension = dimensions.plot_tension
        self.emotional_tension = dimensions.emotional_tension
        self.pacing_tension = dimensions.pacing_tension
        self.tension_score = dimensions.composite_score
        self.updated_at = datetime.utcnow()
