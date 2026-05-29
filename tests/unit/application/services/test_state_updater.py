import pytest
from unittest.mock import Mock
from application.services.state_updater import StateUpdater
from domain.novel.value_objects.chapter_state import ChapterState
from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.entities.plot_arc import PlotArc
from domain.novel.value_objects.event_timeline import EventTimeline
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel
)
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.bible.repositories.bible_repository import BibleRepository


class TestStateUpdater:
    """测试 StateUpdater 应用服务"""

    def setup_method(self):
        """设置测试环境"""
        self.bible_repository = Mock(spec=BibleRepository)
        self.foreshadowing_repository = Mock(spec=ForeshadowingRepository)

        self.updater = StateUpdater(
            bible_repository=self.bible_repository,
            foreshadowing_repository=self.foreshadowing_repository
        )

        self.novel_id = NovelId("novel-1")
        self.bible = Bible(id="bible-1", novel_id=self.novel_id)
        self.foreshadowing_registry = ForeshadowingRegistry(id="foreshadow-1", novel_id=self.novel_id)

    def test_update_from_chapter_empty_state(self):
        """测试从空状态更新"""
        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[],
            events=[]
        )

        # Mock repository returns
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        # 验证没有保存操作（因为没有变化）
        assert self.bible_repository.save.call_count == 0
        assert self.foreshadowing_repository.save.call_count == 0

    def test_update_from_chapter_with_new_characters(self):
        """测试更新包含新角色的状态"""
        chapter_state = ChapterState(
            new_characters=[
                {
                    "name": "张三",
                    "description": "勇敢的战士",
                    "first_appearance": 5
                }
            ],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[],
            events=[]
        )

        # Mock repository returns
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        # 验证 Bible 被保存
        self.bible_repository.save.assert_called_once()
        saved_bible = self.bible_repository.save.call_args[0][0]
        assert len(saved_bible.characters) == 1
        assert saved_bible.characters[0].name == "张三"

    def test_update_from_chapter_with_foreshadowing_planted(self):
        """测试更新包含新伏笔的状态"""
        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[
                {
                    "description": "神秘的预言",
                    "chapter": 5
                }
            ],
            foreshadowing_resolved=[],
            events=[]
        )

        # Mock repository returns
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        # 验证 ForeshadowingRegistry 被保存
        self.foreshadowing_repository.save.assert_called_once()
        saved_registry = self.foreshadowing_repository.save.call_args[0][0]
        assert len(saved_registry.foreshadowings) == 1
        assert saved_registry.foreshadowings[0].description == "神秘的预言"

    def test_update_from_chapter_with_foreshadowing_resolved(self):
        """测试更新包含解决伏笔的状态"""
        # 先添加一个伏笔
        foreshadowing = Foreshadowing(
            id="f-1",
            planted_in_chapter=1,
            description="神秘的预言",
            importance=ImportanceLevel.HIGH,
            status=ForeshadowingStatus.PLANTED
        )
        self.foreshadowing_registry.register(foreshadowing)

        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[
                {
                    "foreshadowing_id": "f-1",
                    "chapter": 10
                }
            ],
            events=[]
        )

        # Mock repository returns
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=10,
            chapter_state=chapter_state
        )

        # 验证 ForeshadowingRegistry 被保存
        self.foreshadowing_repository.save.assert_called_once()
        saved_registry = self.foreshadowing_repository.save.call_args[0][0]
        resolved_foreshadowing = saved_registry.get_by_id("f-1")
        assert resolved_foreshadowing.status == ForeshadowingStatus.RESOLVED
        assert resolved_foreshadowing.resolved_in_chapter == 10

    def test_update_from_chapter_with_multiple_updates(self):
        """测试更新包含多种变化的状态"""
        chapter_state = ChapterState(
            new_characters=[
                {
                    "name": "张三",
                    "description": "勇敢的战士",
                    "first_appearance": 5
                }
            ],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[
                {
                    "description": "神秘的预言",
                    "chapter": 5
                }
            ],
            foreshadowing_resolved=[],
            events=[]
        )

        # Mock repository returns
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        # 验证两个 repository 都被保存
        self.bible_repository.save.assert_called_once()
        self.foreshadowing_repository.save.assert_called_once()

    def test_update_from_chapter_bible_not_found(self):
        """测试 Bible 不存在时的处理"""
        chapter_state = ChapterState(
            new_characters=[
                {
                    "name": "张三",
                    "description": "勇敢的战士",
                    "first_appearance": 5
                }
            ],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[],
            events=[]
        )

        # Mock repository returns None
        self.bible_repository.get_by_novel_id.return_value = None
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        with pytest.raises(ValueError, match="Bible not found"):
            self.updater.update_from_chapter(
                novel_id="novel-1",
                chapter_number=5,
                chapter_state=chapter_state
            )

    def test_update_from_chapter_foreshadowing_registry_not_found(self):
        """ForeshadowingRegistry 不存在时创建新注册表并保存"""
        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[
                {
                    "description": "神秘的预言",
                    "chapter": 5
                }
            ],
            foreshadowing_resolved=[],
            events=[]
        )

        # Mock repository returns None
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = None

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        self.foreshadowing_repository.save.assert_called_once()
        saved_registry = self.foreshadowing_repository.save.call_args[0][0]
        assert len(saved_registry.foreshadowings) == 1
        assert saved_registry.foreshadowings[0].description == "神秘的预言"
