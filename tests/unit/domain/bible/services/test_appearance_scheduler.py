import pytest
# Import directly from module files to avoid circular import
import sys
sys.path.insert(0, '/d/CODE/Plotpilot')
from domain.bible.entities.character import Character
from domain.bible.value_objects.character_id import CharacterId
from domain.bible.value_objects.character_importance import CharacterImportance
from domain.bible.value_objects.activity_metrics import ActivityMetrics
from domain.bible.services.appearance_scheduler import AppearanceScheduler


class TestAppearanceScheduler:
    """测试角色出场调度器"""

    def test_schedule_appearances_with_mentioned_characters(self):
        """测试：大纲中提到的角色优先级最高"""
        # Arrange
        char1 = Character(CharacterId("char1"), "Alice", "Protagonist")
        char2 = Character(CharacterId("char2"), "Bob", "Supporting")
        char3 = Character(CharacterId("char3"), "Charlie", "Minor")

        available = [
            (char1, CharacterImportance.PROTAGONIST, ActivityMetrics()),
            (char2, CharacterImportance.MAJOR_SUPPORTING, ActivityMetrics()),
            (char3, CharacterImportance.MINOR, ActivityMetrics())
        ]

        outline = "Alice meets Bob at the cafe"
        scheduler = AppearanceScheduler()

        # Act
        selected = scheduler.schedule_appearances(outline, available, max_characters=2)

        # Assert
        assert len(selected) == 2
        assert char1 in selected
        assert char2 in selected
        assert char3 not in selected

    def test_schedule_appearances_by_importance(self):
        """测试：未提到时按重要性排序"""
        # Arrange
        char1 = Character(CharacterId("char1"), "Alice", "Protagonist")
        char2 = Character(CharacterId("char2"), "Bob", "Supporting")
        char3 = Character(CharacterId("char3"), "Charlie", "Minor")

        available = [
            (char1, CharacterImportance.PROTAGONIST, ActivityMetrics()),
            (char2, CharacterImportance.MAJOR_SUPPORTING, ActivityMetrics()),
            (char3, CharacterImportance.MINOR, ActivityMetrics())
        ]

        outline = "A mysterious event occurs"
        scheduler = AppearanceScheduler()

        # Act
        selected = scheduler.schedule_appearances(outline, available, max_characters=2)

        # Assert
        assert len(selected) == 2
        assert char1 in selected
        assert char2 in selected

    def test_schedule_appearances_considers_recent_activity(self):
        """测试：考虑最近活动度"""
        # Arrange
        char1 = Character(CharacterId("char1"), "Alice", "Character 1")
        char2 = Character(CharacterId("char2"), "Bob", "Character 2")

        metrics1 = ActivityMetrics()
        metrics1.update_activity(5, 10)  # Recent activity

        metrics2 = ActivityMetrics()
        metrics2.update_activity(1, 5)  # Old activity

        available = [
            (char1, CharacterImportance.IMPORTANT_SUPPORTING, metrics1),
            (char2, CharacterImportance.IMPORTANT_SUPPORTING, metrics2)
        ]

        outline = "Something happens"
        scheduler = AppearanceScheduler()

        # Act
        selected = scheduler.schedule_appearances(outline, available, max_characters=1)

        # Assert
        assert len(selected) == 1
        assert char1 in selected

    def test_schedule_appearances_respects_max_limit(self):
        """测试：遵守最大角色数限制"""
        # Arrange
        chars = [
            (Character(CharacterId(f"char{i}"), f"Char{i}", f"Desc{i}"),
             CharacterImportance.IMPORTANT_SUPPORTING,
             ActivityMetrics())
            for i in range(10)
        ]

        outline = "Many characters"
        scheduler = AppearanceScheduler()

        # Act
        selected = scheduler.schedule_appearances(outline, chars, max_characters=3)

        # Assert
        assert len(selected) == 3

    def test_schedule_appearances_empty_available(self):
        """测试：空角色列表"""
        # Arrange
        scheduler = AppearanceScheduler()

        # Act
        selected = scheduler.schedule_appearances("outline", [], max_characters=5)

        # Assert
        assert len(selected) == 0

    def test_schedule_appearances_all_mentioned(self):
        """测试：所有角色都在大纲中提到"""
        # Arrange
        char1 = Character(CharacterId("char1"), "Alice", "Protagonist")
        char2 = Character(CharacterId("char2"), "Bob", "Supporting")

        available = [
            (char1, CharacterImportance.PROTAGONIST, ActivityMetrics()),
            (char2, CharacterImportance.MAJOR_SUPPORTING, ActivityMetrics())
        ]

        outline = "Alice and Bob have a conversation"
        scheduler = AppearanceScheduler()

        # Act
        selected = scheduler.schedule_appearances(outline, available, max_characters=10)

        # Assert
        assert len(selected) == 2
        assert char1 in selected
        assert char2 in selected
