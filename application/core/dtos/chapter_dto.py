"""Chapter 数据传输对象"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.novel.entities.chapter import Chapter


@dataclass
class ChapterDTO:
    """章节 DTO"""
    id: str
    novel_id: str
    number: int
    title: str
    content: str
    word_count: int
    status: str
    generation_hint: str = ""

    @classmethod
    def from_domain(cls, chapter: 'Chapter') -> 'ChapterDTO':
        """从领域对象创建 DTO

        Args:
            chapter: Chapter 领域对象

        Returns:
            ChapterDTO
        """
        # 处理 novel_id 和 status 可能是字符串或值对象的情况
        novel_id = chapter.novel_id.value if hasattr(chapter.novel_id, 'value') else chapter.novel_id
        status = chapter.status.value if hasattr(chapter.status, 'value') else chapter.status

        return cls(
            id=chapter.id,
            novel_id=novel_id,
            number=chapter.number,
            title=chapter.title,
            content=chapter.content,
            word_count=chapter.word_count.value,
            status=status,
            generation_hint=getattr(chapter, 'generation_hint', '') or '',
        )
