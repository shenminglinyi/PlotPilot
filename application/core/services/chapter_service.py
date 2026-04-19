"""Chapter 应用服务"""
from typing import List, Optional, Any
from datetime import datetime
import re
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.novel_repository import NovelRepository
from domain.shared.exceptions import EntityNotFoundError
from application.core.dtos.chapter_dto import ChapterDTO
from application.audit.dtos.chapter_review_dto import ChapterReviewDTO
from application.core.dtos.chapter_structure_dto import ChapterStructureDTO


class ChapterService:
    """Chapter 应用服务"""

    def __init__(
        self,
        chapter_repository: ChapterRepository,
        novel_repository: NovelRepository,
        chapter_review_repository=None,
        chapter_renumber_coordinator: Any = None,
    ):
        """初始化服务

        Args:
            chapter_repository: Chapter 仓储
            novel_repository: Novel 仓储
            chapter_review_repository: Chapter Review 仓储（可选）
            chapter_renumber_coordinator: 删章后伏笔/快照/向量等侧车数据章号重排（可选）
        """
        self.chapter_repository = chapter_repository
        self.novel_repository = novel_repository
        self.chapter_review_repository = chapter_review_repository
        self._chapter_renumber_coordinator = chapter_renumber_coordinator

    def update_chapter_content(
        self,
        chapter_id: str,
        content: str
    ) -> ChapterDTO:
        """更新章节内容

        Args:
            chapter_id: 章节 ID
            content: 内容

        Returns:
            更新后的 ChapterDTO

        Raises:
            EntityNotFoundError: 如果章节不存在
        """
        chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
        if chapter is None:
            raise EntityNotFoundError("Chapter", chapter_id)

        chapter.update_content(content)
        self.chapter_repository.save(chapter)

        return ChapterDTO.from_domain(chapter)

    def list_chapters_by_novel(self, novel_id: str) -> List[ChapterDTO]:
        """列出小说的所有章节

        Args:
            novel_id: 小说 ID

        Returns:
            ChapterDTO 列表
        """
        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        return [ChapterDTO.from_domain(chapter) for chapter in chapters]

    def get_chapter(self, chapter_id: str) -> Optional[ChapterDTO]:
        """获取章节

        Args:
            chapter_id: 章节 ID

        Returns:
            ChapterDTO 或 None
        """
        chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
        if chapter is None:
            return None
        return ChapterDTO.from_domain(chapter)

    def delete_chapter(self, chapter_id: str) -> None:
        """删除章节

        Args:
            chapter_id: 章节 ID
        """
        chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
        if chapter is None:
            return
        novel_id = (
            chapter.novel_id.value
            if hasattr(chapter.novel_id, "value")
            else chapter.novel_id
        )
        deleted_number = chapter.number
        self.chapter_repository.delete(ChapterId(chapter_id))
        coordinator = self._chapter_renumber_coordinator
        if coordinator is not None:
            coordinator.on_chapter_deleted(novel_id, deleted_number)

    def get_chapter_by_novel_and_number(
        self,
        novel_id: str,
        chapter_number: int
    ) -> Optional[ChapterDTO]:
        """根据小说 ID 和章节号获取章节

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            ChapterDTO 或 None
        """
        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        for chapter in chapters:
            if chapter.number == chapter_number:
                return ChapterDTO.from_domain(chapter)
        return None

    def update_chapter_by_novel_and_number(
        self,
        novel_id: str,
        chapter_number: int,
        content: str
    ) -> Optional[ChapterDTO]:
        """根据小说 ID 和章节号更新章节内容

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            content: 新内容

        Returns:
            更新后的 ChapterDTO 或 None

        Raises:
            EntityNotFoundError: 如果章节不存在
        """
        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        for chapter in chapters:
            if chapter.number == chapter_number:
                chapter.update_content(content)
                self.chapter_repository.save(chapter)
                return ChapterDTO.from_domain(chapter)
        raise EntityNotFoundError("Chapter", f"{novel_id}/chapter-{chapter_number}")

    def get_chapter_review(
        self,
        novel_id: str,
        chapter_number: int
    ) -> ChapterReviewDTO:
        """获取章节审阅

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            ChapterReviewDTO

        Raises:
            EntityNotFoundError: 如果章节不存在
        """
        # 验证章节存在
        chapter = self._get_chapter_by_novel_and_number(novel_id, chapter_number)
        if chapter is None:
            raise EntityNotFoundError("Chapter", f"{novel_id}/chapter-{chapter_number}")

        # 使用数据库 repository
        if self.chapter_review_repository:
            review = self.chapter_review_repository.get(novel_id, chapter_number)
            if review:
                return review

        # 返回默认审阅
        now = datetime.utcnow()
        return ChapterReviewDTO(
            status="draft",
            memo="",
            created_at=now,
            updated_at=now
        )

    def save_chapter_review(
        self,
        novel_id: str,
        chapter_number: int,
        status: str,
        memo: str
    ) -> ChapterReviewDTO:
        """保存章节审阅

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            status: 审阅状态
            memo: 审阅备注

        Returns:
            ChapterReviewDTO

        Raises:
            EntityNotFoundError: 如果章节不存在
        """
        # 验证章节存在
        chapter = self._get_chapter_by_novel_and_number(novel_id, chapter_number)
        if chapter is None:
            raise EntityNotFoundError("Chapter", f"{novel_id}/chapter-{chapter_number}")

        # 使用数据库 repository
        if self.chapter_review_repository:
            return self.chapter_review_repository.upsert(
                novel_id, chapter_number, status=status, memo=memo
            )

        # 降级：返回临时对象（不应该到达这里）
        now = datetime.utcnow()
        return ChapterReviewDTO(
            status=status,
            memo=memo,
            created_at=now,
            updated_at=now
        )

    def get_chapter_structure(
        self,
        novel_id: str,
        chapter_number: int
    ) -> ChapterStructureDTO:
        """获取章节结构分析

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            ChapterStructureDTO

        Raises:
            EntityNotFoundError: 如果章节不存在
        """
        chapter = self._get_chapter_by_novel_and_number(novel_id, chapter_number)
        if chapter is None:
            raise EntityNotFoundError("Chapter", f"{novel_id}/chapter-{chapter_number}")

        content = chapter.content

        # 分析章节结构
        if not content or not content.strip():
            return ChapterStructureDTO(
                word_count=0,
                paragraph_count=0,
                dialogue_ratio=0.0,
                scene_count=0,
                pacing="medium"
            )

        # 计算字数（中文字符 + 英文单词）
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', content))
        word_count = chinese_chars + english_words

        # 计算段落数（非空行）
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        paragraph_count = len(paragraphs)

        # 计算对话比例（引号内的内容）
        dialogue_chars = 0
        for match in re.finditer(r'["""](.*?)["""]', content):
            dialogue_chars += len(match.group(1))
        dialogue_ratio = dialogue_chars / word_count if word_count > 0 else 0.0

        # 计算场景数（通过分隔符或空行判断）
        scene_count = len(re.findall(r'---+|\n\n\n+', content)) + 1

        # 判断节奏（基于平均段落长度）
        avg_paragraph_length = word_count / paragraph_count if paragraph_count > 0 else 0
        if avg_paragraph_length < 30:
            pacing = "fast"
        elif avg_paragraph_length > 80:
            pacing = "slow"
        else:
            pacing = "medium"

        return ChapterStructureDTO(
            word_count=word_count,
            paragraph_count=paragraph_count,
            dialogue_ratio=round(dialogue_ratio, 2),
            scene_count=scene_count,
            pacing=pacing
        )

    def ensure_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        title: str = ""
    ) -> ChapterDTO:
        """确保章节在正文库中存在；不存在则创建空白记录（不校验章节号连续性）。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            title: 章节标题（可选，默认为 "第N章"）

        Returns:
            ChapterDTO
        """
        existing = self.get_chapter_by_novel_and_number(novel_id, chapter_number)
        if existing:
            return existing

        chapter_title = title.strip() if title and title.strip() else f"第{chapter_number}章"
        chapter_id = f"chapter-{novel_id}-{chapter_number}"
        chapter = Chapter(
            id=chapter_id,
            novel_id=NovelId(novel_id),
            number=chapter_number,
            title=chapter_title,
            content="",
            status=ChapterStatus.DRAFT,
        )
        self.chapter_repository.save(chapter)
        return ChapterDTO.from_domain(chapter)

    def _get_chapter_by_novel_and_number(
        self,
        novel_id: str,
        chapter_number: int
    ) -> Optional[Chapter]:
        """根据小说 ID 和章节号获取章节实体

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            Chapter 实体或 None
        """
        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        for chapter in chapters:
            if chapter.number == chapter_number:
                return chapter
        return None
