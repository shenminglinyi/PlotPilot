"""端到端集成测试 - Novel 工作流"""
import pytest
import tempfile
import shutil
from pathlib import Path
from infrastructure.persistence.storage.file_storage import FileStorage
from infrastructure.persistence.repositories.file_novel_repository import FileNovelRepository
from infrastructure.persistence.repositories.file_chapter_repository import FileChapterRepository
from application.services.novel_service import NovelService


class TestNovelWorkflow:
    """Novel 完整工作流集成测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path)

    @pytest.fixture
    def service(self, temp_dir):
        """创建完整的服务栈"""
        storage = FileStorage(temp_dir)
        novel_repo = FileNovelRepository(storage)
        chapter_repo = FileChapterRepository(storage)
        return NovelService(novel_repo, chapter_repo)

    def test_complete_novel_workflow(self, service):
        """测试完整的小说创建和管理流程"""
        # 1. 创建小说
        novel_dto = service.create_novel(
            novel_id="test-novel",
            title="测试小说",
            author="测试作者",
            target_chapters=3
        )

        assert novel_dto.id == "test-novel"
        assert novel_dto.title == "测试小说"
        assert novel_dto.stage == "planning"
        assert len(novel_dto.chapters) == 0

        # 2. 添加第一章
        novel_dto = service.add_chapter(
            novel_id="test-novel",
            chapter_id="chapter-1",
            number=1,
            title="第一章：开始",
            content="这是第一章的内容。"
        )

        assert len(novel_dto.chapters) == 1
        assert novel_dto.chapters[0].title == "第一章：开始"
        assert novel_dto.total_word_count == 9

        # 3. 添加第二章
        novel_dto = service.add_chapter(
            novel_id="test-novel",
            chapter_id="chapter-2",
            number=2,
            title="第二章：发展",
            content="这是第二章的内容，更长一些。"
        )

        assert len(novel_dto.chapters) == 2
        assert novel_dto.total_word_count == 23

        # 4. 获取小说
        retrieved = service.get_novel("test-novel")
        assert retrieved is not None
        assert retrieved.id == "test-novel"
        assert len(retrieved.chapters) == 2

        # 5. 列出所有小说
        novels = service.list_novels()
        assert len(novels) == 1
        assert novels[0].id == "test-novel"

        # 6. 删除小说
        service.delete_novel("test-novel")

        # 7. 验证删除
        deleted = service.get_novel("test-novel")
        assert deleted is None

    def test_multiple_novels(self, service):
        """测试管理多本小说"""
        # 创建三本小说
        service.create_novel("novel-1", "小说1", "作者1", 5)
        service.create_novel("novel-2", "小说2", "作者2", 10)
        service.create_novel("novel-3", "小说3", "作者3", 15)

        # 列出所有小说
        novels = service.list_novels()
        assert len(novels) == 3

        novel_ids = [n.id for n in novels]
        assert "novel-1" in novel_ids
        assert "novel-2" in novel_ids
        assert "novel-3" in novel_ids

    def test_novel_with_multiple_chapters(self, service):
        """测试包含多个章节的小说"""
        # 创建小说
        service.create_novel("novel", "测试", "作者", 5)

        # 添加5个章节
        for i in range(1, 6):
            service.add_chapter(
                novel_id="novel",
                chapter_id=f"chapter-{i}",
                number=i,
                title=f"第{i}章",
                content=f"这是第{i}章的内容。" * 10
            )

        # 验证
        novel = service.get_novel("novel")
        assert len(novel.chapters) == 5
        assert novel.total_word_count == 450

        # 验证章节顺序
        for i, chapter in enumerate(novel.chapters, 1):
            assert chapter.number == i
            assert chapter.title == f"第{i}章"

    def test_novel_metadata_fields(self, service, temp_dir):
        """测试小说元数据字段（has_bible, has_outline）"""
        # 创建小说
        service.create_novel("novel-meta", "测试元数据", "作者", 5)

        # 初始状态：没有 bible 和 outline
        novel = service.get_novel("novel-meta")
        assert novel.has_bible is False
        assert novel.has_outline is False

        # 创建 bible.json 文件
        bible_path = temp_dir / "novels" / "novel-meta" / "bible.json"
        bible_path.parent.mkdir(parents=True, exist_ok=True)
        bible_path.write_text('{"characters": []}')

        # 再次获取，应该检测到 bible
        novel = service.get_novel("novel-meta")
        assert novel.has_bible is True
        assert novel.has_outline is False

        # 创建 outline.json 文件
        outline_path = temp_dir / "novels" / "novel-meta" / "outline.json"
        outline_path.write_text('{"chapters": []}')

        # 再次获取，应该检测到两者
        novel = service.get_novel("novel-meta")
        assert novel.has_bible is True
        assert novel.has_outline is True
