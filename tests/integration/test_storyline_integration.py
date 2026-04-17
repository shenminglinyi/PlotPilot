import pytest
import tempfile
import shutil
from pathlib import Path
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_milestone import StorylineMilestone
from domain.novel.services.storyline_manager import StorylineManager
from infrastructure.persistence.repositories.file_storyline_repository import FileStorylineRepository
from infrastructure.persistence.storage.file_storage import FileStorage


class TestStorylineIntegration:
    """故事线管理系统集成测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def storyline_manager(self, temp_dir):
        """创建故事线管理器"""
        storage = FileStorage(temp_dir)
        repository = FileStorylineRepository(storage)
        return StorylineManager(repository)

    def test_create_and_retrieve_storyline(self, storyline_manager):
        """测试创建和检索故事线"""
        novel_id = NovelId("novel-123")

        # Create storyline
        storyline = storyline_manager.create_storyline(
            novel_id=novel_id,
            storyline_type=StorylineType.ROMANCE,
            estimated_chapter_start=5,
            estimated_chapter_end=20
        )

        assert storyline.id is not None
        assert storyline.novel_id == novel_id
        assert storyline.storyline_type == StorylineType.ROMANCE
        assert storyline.status == StorylineStatus.ACTIVE

        # Retrieve storyline
        retrieved = storyline_manager.repository.get_by_id(storyline.id)
        assert retrieved is not None
        assert retrieved.id == storyline.id
        assert retrieved.novel_id == novel_id

    def test_storyline_with_milestones_workflow(self, storyline_manager):
        """测试带有里程碑的故事线完整工作流"""
        novel_id = NovelId("novel-456")

        # Create storyline
        storyline = storyline_manager.create_storyline(
            novel_id=novel_id,
            storyline_type=StorylineType.MYSTERY,
            estimated_chapter_start=1,
            estimated_chapter_end=30
        )

        # Add milestones
        milestone1 = StorylineMilestone(
            order=0,
            title="Discovery",
            description="The mystery is discovered",
            target_chapter_start=1,
            target_chapter_end=3,
            prerequisites=[],
            triggers=["mystery_found"]
        )
        milestone2 = StorylineMilestone(
            order=1,
            title="Investigation",
            description="Clues are gathered",
            target_chapter_start=5,
            target_chapter_end=15,
            prerequisites=["mystery_found"],
            triggers=["clues_gathered"]
        )
        milestone3 = StorylineMilestone(
            order=2,
            title="Resolution",
            description="Mystery is solved",
            target_chapter_start=25,
            target_chapter_end=30,
            prerequisites=["clues_gathered"],
            triggers=["solved"]
        )

        storyline.add_milestone(milestone1)
        storyline.add_milestone(milestone2)
        storyline.add_milestone(milestone3)
        storyline_manager.repository.save(storyline)

        # Get pending milestones
        pending = storyline_manager.get_pending_milestones(storyline.id)
        assert len(pending) == 3
        assert pending[0].title == "Discovery"

        # Complete first milestone
        storyline_manager.complete_milestone(storyline.id, 0)

        # Check pending milestones again
        pending = storyline_manager.get_pending_milestones(storyline.id)
        assert len(pending) == 2
        assert pending[0].title == "Investigation"

        # Get storyline context
        context = storyline_manager.get_storyline_context(storyline.id)
        assert "mystery" in context.lower()
        assert "Investigation" in context
        assert "Clues are gathered" in context

    def test_multiple_storylines_for_novel(self, storyline_manager):
        """测试一个小说有多条故事线"""
        novel_id = NovelId("novel-789")

        # Create multiple storylines
        romance = storyline_manager.create_storyline(
            novel_id=novel_id,
            storyline_type=StorylineType.ROMANCE,
            estimated_chapter_start=5,
            estimated_chapter_end=25
        )

        revenge = storyline_manager.create_storyline(
            novel_id=novel_id,
            storyline_type=StorylineType.REVENGE,
            estimated_chapter_start=1,
            estimated_chapter_end=30
        )

        growth = storyline_manager.create_storyline(
            novel_id=novel_id,
            storyline_type=StorylineType.GROWTH,
            estimated_chapter_start=1,
            estimated_chapter_end=30
        )

        # Retrieve all storylines for the novel
        storylines = storyline_manager.repository.get_by_novel_id(novel_id)
        assert len(storylines) == 3

        storyline_types = {s.storyline_type for s in storylines}
        assert StorylineType.ROMANCE in storyline_types
        assert StorylineType.REVENGE in storyline_types
        assert StorylineType.GROWTH in storyline_types

    def test_delete_storyline(self, storyline_manager):
        """测试删除故事线"""
        novel_id = NovelId("novel-delete")

        # Create storyline
        storyline = storyline_manager.create_storyline(
            novel_id=novel_id,
            storyline_type=StorylineType.ADVENTURE,
            estimated_chapter_start=1,
            estimated_chapter_end=20
        )

        # Verify it exists
        retrieved = storyline_manager.repository.get_by_id(storyline.id)
        assert retrieved is not None

        # Delete it
        storyline_manager.repository.delete(storyline.id)

        # Verify it's gone
        retrieved = storyline_manager.repository.get_by_id(storyline.id)
        assert retrieved is None

    def test_complete_milestone_validation(self, storyline_manager):
        """测试完成里程碑的验证"""
        novel_id = NovelId("novel-validation")

        # Create storyline with milestones
        storyline = storyline_manager.create_storyline(
            novel_id=novel_id,
            storyline_type=StorylineType.POLITICAL,
            estimated_chapter_start=1,
            estimated_chapter_end=50
        )

        milestone1 = StorylineMilestone(
            order=0,
            title="First",
            description="First milestone",
            target_chapter_start=1,
            target_chapter_end=10,
            prerequisites=[],
            triggers=[]
        )
        milestone2 = StorylineMilestone(
            order=1,
            title="Second",
            description="Second milestone",
            target_chapter_start=20,
            target_chapter_end=30,
            prerequisites=[],
            triggers=[]
        )

        storyline.add_milestone(milestone1)
        storyline.add_milestone(milestone2)
        storyline_manager.repository.save(storyline)

        # Try to complete second milestone before first
        with pytest.raises(ValueError, match="Cannot complete milestone 1 before completing milestone 0"):
            storyline_manager.complete_milestone(storyline.id, 1)

        # Complete first milestone
        storyline_manager.complete_milestone(storyline.id, 0)

        # Now complete second milestone should work
        storyline_manager.complete_milestone(storyline.id, 1)

        # All milestones completed
        pending = storyline_manager.get_pending_milestones(storyline.id)
        assert len(pending) == 0
