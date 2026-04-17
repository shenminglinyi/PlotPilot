"""ChapterService 单元测试"""
import pytest
from unittest.mock import Mock
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.novel_id import NovelId
from domain.shared.exceptions import EntityNotFoundError
from application.services.chapter_service import ChapterService


class TestChapterService:
    """ChapterService 单元测试"""

    @pytest.fixture
    def mock_chapter_repository(self):
        """创建 mock 章节仓储"""
        return Mock()

    @pytest.fixture
    def mock_novel_repository(self):
        """创建 mock 小说仓储"""
        return Mock()

    @pytest.fixture
    def service(self, mock_chapter_repository, mock_novel_repository):
        """创建服务实例"""
        return ChapterService(mock_chapter_repository, mock_novel_repository)

    def test_update_chapter_content(self, service, mock_chapter_repository):
        """测试更新章节内容"""
        # 准备 mock 数据
        chapter = Chapter(
            id="chapter-1",
            novel_id=NovelId("novel-1"),
            number=1,
            title="第一章",
            content="原始内容"
        )
        mock_chapter_repository.get_by_id.return_value = chapter

        chapter_dto = service.update_chapter_content(
            chapter_id="chapter-1",
            content="更新后的内容"
        )

        assert chapter_dto.id == "chapter-1"
        assert chapter_dto.content == "更新后的内容"

        # 验证调用了 save
        mock_chapter_repository.save.assert_called_once()

    def test_update_chapter_content_not_found(self, service, mock_chapter_repository):
        """测试更新不存在的章节内容"""
        mock_chapter_repository.get_by_id.return_value = None

        with pytest.raises(EntityNotFoundError, match="Chapter"):
            service.update_chapter_content(
                chapter_id="nonexistent",
                content="新内容"
            )

    def test_list_chapters_by_novel(self, service, mock_chapter_repository):
        """测试列出小说的所有章节"""
        # 准备 mock 数据
        chapter1 = Chapter(
            id="chapter-1",
            novel_id=NovelId("novel-1"),
            number=1,
            title="第一章",
            content="内容1"
        )
        chapter2 = Chapter(
            id="chapter-2",
            novel_id=NovelId("novel-1"),
            number=2,
            title="第二章",
            content="内容2"
        )
        mock_chapter_repository.list_by_novel.return_value = [chapter1, chapter2]

        chapters = service.list_chapters_by_novel("novel-1")

        assert len(chapters) == 2
        assert chapters[0].id == "chapter-1"
        assert chapters[1].id == "chapter-2"

        mock_chapter_repository.list_by_novel.assert_called_once_with(NovelId("novel-1"))

    def test_get_chapter(self, service, mock_chapter_repository):
        """测试获取章节"""
        # 准备 mock 数据
        chapter = Chapter(
            id="chapter-1",
            novel_id=NovelId("novel-1"),
            number=1,
            title="第一章",
            content="内容"
        )
        mock_chapter_repository.get_by_id.return_value = chapter

        chapter_dto = service.get_chapter("chapter-1")

        assert chapter_dto is not None
        assert chapter_dto.id == "chapter-1"
        assert chapter_dto.title == "第一章"

        mock_chapter_repository.get_by_id.assert_called_once_with(ChapterId("chapter-1"))

    def test_get_chapter_not_found(self, service, mock_chapter_repository):
        """测试获取不存在的章节"""
        mock_chapter_repository.get_by_id.return_value = None

        chapter_dto = service.get_chapter("nonexistent")

        assert chapter_dto is None

    def test_delete_chapter(self, service, mock_chapter_repository):
        """测试删除章节"""
        service.delete_chapter("chapter-1")

        mock_chapter_repository.delete.assert_called_once_with(ChapterId("chapter-1"))
