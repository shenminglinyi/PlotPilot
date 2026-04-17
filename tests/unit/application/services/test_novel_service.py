"""NovelService 单元测试"""
import pytest
from unittest.mock import Mock
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.word_count import WordCount
from domain.novel.value_objects.chapter_content import ChapterContent
from domain.shared.exceptions import EntityNotFoundError
from application.services.novel_service import NovelService
from application.dtos.novel_dto import NovelDTO


class TestNovelService:
    """NovelService 单元测试"""

    @pytest.fixture
    def mock_repository(self):
        """创建 mock 仓储"""
        return Mock()

    @pytest.fixture
    def mock_chapter_repository(self):
        return Mock()

    @pytest.fixture
    def mock_generation_metrics_repository(self):
        return Mock()

    @pytest.fixture
    def service(self, mock_repository, mock_chapter_repository, mock_generation_metrics_repository):
        """创建服务实例"""
        return NovelService(
            mock_repository,
            mock_chapter_repository,
            chapter_generation_metrics_repository=mock_generation_metrics_repository,
        )

    def test_create_novel(self, service, mock_repository):
        """测试创建小说"""
        novel_dto = service.create_novel(
            novel_id="test-novel",
            title="测试小说",
            author="测试作者",
            target_chapters=10
        )

        assert novel_dto.id == "test-novel"
        assert novel_dto.title == "测试小说"
        assert novel_dto.author == "测试作者"
        assert novel_dto.target_chapters == 10
        assert novel_dto.target_words_per_chapter == 3500
        assert novel_dto.stage == "planning"

        # 验证调用了 save
        mock_repository.save.assert_called_once()

    def test_get_novel(self, service, mock_repository):
        """测试获取小说"""
        # 准备 mock 数据
        novel = Novel(
            id=NovelId("test-novel"),
            title="测试小说",
            author="测试作者",
            target_chapters=10
        )
        mock_repository.get_by_id.return_value = novel
        mock_repository.storage.exists.side_effect = lambda path: path == "novels/test-novel/bible.json"

        novel_dto = service.get_novel("test-novel")

        assert novel_dto is not None
        assert novel_dto.id == "test-novel"
        assert novel_dto.title == "测试小说"
        assert novel_dto.has_bible is True
        assert novel_dto.has_outline is False

        mock_repository.get_by_id.assert_called_once_with(NovelId("test-novel"))

    def test_get_novel_not_found(self, service, mock_repository):
        """测试获取不存在的小说"""
        mock_repository.get_by_id.return_value = None

        novel_dto = service.get_novel("nonexistent")

        assert novel_dto is None

    def test_list_novels(self, service, mock_repository):
        """测试列出所有小说"""
        # 准备 mock 数据
        novel1 = Novel(
            id=NovelId("novel-1"),
            title="小说1",
            author="作者1",
            target_chapters=10
        )
        novel2 = Novel(
            id=NovelId("novel-2"),
            title="小说2",
            author="作者2",
            target_chapters=20
        )
        mock_repository.list_all.return_value = [novel1, novel2]

        novels = service.list_novels()

        assert len(novels) == 2
        assert novels[0].id == "novel-1"
        assert novels[1].id == "novel-2"

    def test_delete_novel(self, service, mock_repository):
        """测试删除小说"""
        service.delete_novel("test-novel")

        mock_repository.delete.assert_called_once_with(NovelId("test-novel"))

    def test_add_chapter(self, service, mock_repository):
        """测试添加章节"""
        # 准备 mock 数据
        novel = Novel(
            id=NovelId("test-novel"),
            title="测试小说",
            author="测试作者",
            target_chapters=10
        )
        mock_repository.get_by_id.return_value = novel

        novel_dto = service.add_chapter(
            novel_id="test-novel",
            chapter_id="chapter-1",
            number=1,
            title="第一章",
            content="章节内容"
        )

        assert len(novel_dto.chapters) == 1
        assert novel_dto.chapters[0].id == "chapter-1"
        assert novel_dto.chapters[0].title == "第一章"

        # 验证调用了 save
        mock_repository.save.assert_called_once()

    def test_add_chapter_novel_not_found(self, service, mock_repository):
        """测试向不存在的小说添加章节"""
        mock_repository.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Novel not found"):
            service.add_chapter(
                novel_id="nonexistent",
                chapter_id="chapter-1",
                number=1,
                title="第一章",
                content="章节内容"
            )

    def test_update_novel_stage(self, service, mock_repository):
        """测试更新小说阶段"""
        # 准备 mock 数据
        novel = Novel(
            id=NovelId("test-novel"),
            title="测试小说",
            author="测试作者",
            target_chapters=10,
            stage=NovelStage.PLANNING
        )
        mock_repository.get_by_id.return_value = novel

        novel_dto = service.update_novel_stage("test-novel", "writing")

        assert novel_dto.stage == "writing"

        # 验证调用了 save
        mock_repository.save.assert_called_once()

    def test_update_novel_stage_not_found(self, service, mock_repository):
        """测试更新不存在的小说阶段"""
        mock_repository.get_by_id.return_value = None

        with pytest.raises(EntityNotFoundError, match="Novel"):
            service.update_novel_stage("nonexistent", "writing")

    def test_get_novel_statistics(self, service, mock_repository, mock_chapter_repository, mock_generation_metrics_repository):
        """测试获取小说统计信息（章节来自 Chapter 仓储）"""
        novel = Novel(
            id=NovelId("test-novel"),
            title="测试小说",
            author="测试作者",
            target_chapters=10,
            stage=NovelStage.WRITING
        )
        chapter1 = Chapter(
            id="chapter-1",
            novel_id=NovelId("test-novel"),
            number=1,
            title="第一章",
            content="这是第一章的内容"
        )
        chapter2 = Chapter(
            id="chapter-2",
            novel_id=NovelId("test-novel"),
            number=2,
            title="第二章",
            content=""  # 空内容
        )
        mock_repository.get_by_id.return_value = novel
        mock_chapter_repository.list_by_novel.return_value = [chapter1, chapter2]
        mock_generation_metrics_repository.get_book_summary.return_value = {
            "total_measured": 1,
            "within_tolerance_count": 1,
            "pass_rate": 1.0,
            "expansion_trigger_count": 0,
            "trim_trigger_count": 0,
            "expansion_trigger_rate": 0.0,
            "trim_trigger_rate": 0.0,
            "avg_expansion_attempts": 0.0,
        }

        stats = service.get_novel_statistics("test-novel")

        assert stats["total_chapters"] == 2
        assert stats["completed_chapters"] == 1
        assert stats["stage"] == "writing"
        assert stats["total_words"] > 0
        assert stats["slug"] == "test-novel"
        assert stats["title"] == "测试小说"
        assert "completion_rate" in stats
        assert stats["generation_quality"]["pass_rate"] == 1.0
        mock_chapter_repository.list_by_novel.assert_called_once_with(NovelId("test-novel"))

    def test_get_novel_statistics_not_found(self, service, mock_repository):
        """测试获取不存在的小说统计信息"""
        mock_repository.get_by_id.return_value = None

        with pytest.raises(EntityNotFoundError, match="Novel"):
            service.get_novel_statistics("nonexistent")

    def test_update_novel_updates_target_words_per_chapter(self, service, mock_repository):
        """测试更新每章目标字数"""
        novel = Novel(
            id=NovelId("test-novel"),
            title="测试小说",
            author="测试作者",
            target_chapters=10,
            target_words_per_chapter=3000
        )
        mock_repository.get_by_id.return_value = novel

        novel_dto = service.update_novel(
            "test-novel",
            target_words_per_chapter=4200
        )

        assert novel.target_words_per_chapter == 4200
        assert novel_dto.target_words_per_chapter == 4200
        mock_repository.save.assert_called()
