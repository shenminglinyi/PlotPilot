from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId


class ChapterRepository(ABC):
    """章节仓储接口"""

    @abstractmethod
    def save(self, chapter: Chapter) -> None:
        """保存章节"""
        pass

    @abstractmethod
    def get_by_id(self, chapter_id: ChapterId) -> Optional[Chapter]:
        """根据 ID 获取章节"""
        pass

    @abstractmethod
    def list_by_novel(self, novel_id: NovelId) -> List[Chapter]:
        """
        列出小说的所有章节

        返回的章节列表按章节序号升序排序
        """
        pass

    def completed_revisions(self, novel_id: NovelId) -> dict[int, str]:
        """Manuscript evidence; tree planning rows cannot satisfy closure."""
        import hashlib
        return {
            c.number: hashlib.sha256(c.content.encode('utf-8')).hexdigest()
            for c in self.list_by_novel(novel_id)
            if getattr(c.status, 'value', c.status) == 'completed' and c.content.strip()
        }

    @abstractmethod
    def exists(self, chapter_id: ChapterId) -> bool:
        """检查章节是否存在"""
        pass

    @abstractmethod
    def delete(self, chapter_id: ChapterId) -> None:
        """
        删除章节

        如果章节不存在，此操作不会引发错误
        """
        pass
