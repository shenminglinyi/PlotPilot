"""Tests for NarrativeEntityStateService."""

import pytest
from unittest.mock import Mock
from application.analyst.services.narrative_entity_state_service import NarrativeEntityStateService


class TestNarrativeEntityStateService:
    """Test suite for NarrativeEntityStateService."""

    @pytest.fixture
    def mock_entity_base_repository(self):
        """Create mock entity base repository."""
        return Mock()

    @pytest.fixture
    def mock_narrative_event_repository(self):
        """Create mock narrative event repository."""
        return Mock()

    @pytest.fixture
    def service(self, mock_entity_base_repository, mock_narrative_event_repository):
        """Create service instance."""
        return NarrativeEntityStateService(
            mock_entity_base_repository,
            mock_narrative_event_repository
        )

    def test_get_state_combines_base_and_events(
        self, service, mock_entity_base_repository, mock_narrative_event_repository
    ):
        """Test that get_state combines base attributes with events and replays them."""
        # Arrange: Mock entity base
        entity_base = {
            "id": "entity-1",
            "novel_id": "novel-1",
            "entity_type": "character",
            "name": "张三",
            "core_attributes": {"魔法": "水系", "等级": "5"},
            "created_at": "2026-04-05T00:00:00"
        }
        mock_entity_base_repository.get_by_id.return_value = entity_base

        # Mock events
        events = [
            {
                "event_id": "event-1",
                "novel_id": "novel-1",
                "chapter_number": 1,
                "event_summary": "升级",
                "mutations": [{"attribute": "等级", "action": "add", "value": "10"}],
                "timestamp_ts": "2026-04-05T01:00:00"
            },
            {
                "event_id": "event-2",
                "novel_id": "novel-1",
                "chapter_number": 2,
                "event_summary": "学习新魔法",
                "mutations": [{"attribute": "魔法", "action": "add", "value": "火系"}],
                "timestamp_ts": "2026-04-05T02:00:00"
            }
        ]
        mock_narrative_event_repository.list_up_to_chapter.return_value = events

        # Act
        state = service.get_state("entity-1", 2)

        # Assert: Verify repository calls
        mock_entity_base_repository.get_by_id.assert_called_once_with("entity-1")
        mock_narrative_event_repository.list_up_to_chapter.assert_called_once_with("novel-1", 2)

        # Assert: Verify replay result
        assert state is not None
        assert state["等级"] == "10"  # Updated by event-1
        assert state["魔法"] == "火系"  # Updated by event-2

    def test_get_state_entity_not_found(
        self, service, mock_entity_base_repository, mock_narrative_event_repository
    ):
        """Test that get_state returns None when entity does not exist."""
        # Arrange
        mock_entity_base_repository.get_by_id.return_value = None

        # Act
        state = service.get_state("nonexistent", 10)

        # Assert
        assert state is None
        mock_entity_base_repository.get_by_id.assert_called_once_with("nonexistent")
        # Should not call event repository if entity not found
        mock_narrative_event_repository.list_up_to_chapter.assert_not_called()

    def test_get_state_no_events(
        self, service, mock_entity_base_repository, mock_narrative_event_repository
    ):
        """Test that get_state returns base attributes when no events exist."""
        # Arrange
        entity_base = {
            "id": "entity-1",
            "novel_id": "novel-1",
            "entity_type": "character",
            "name": "张三",
            "core_attributes": {"魔法": "水系", "等级": "5"},
            "created_at": "2026-04-05T00:00:00"
        }
        mock_entity_base_repository.get_by_id.return_value = entity_base
        mock_narrative_event_repository.list_up_to_chapter.return_value = []

        # Act
        state = service.get_state("entity-1", 10)

        # Assert
        assert state is not None
        assert state == {"魔法": "水系", "等级": "5"}  # Same as base
        mock_narrative_event_repository.list_up_to_chapter.assert_called_once_with("novel-1", 10)

    def test_get_state_filters_by_chapter(
        self, service, mock_entity_base_repository, mock_narrative_event_repository
    ):
        """Test that get_state only replays events up to specified chapter."""
        # Arrange
        entity_base = {
            "id": "entity-1",
            "novel_id": "novel-1",
            "entity_type": "character",
            "name": "张三",
            "core_attributes": {"等级": "1"},
            "created_at": "2026-04-05T00:00:00"
        }
        mock_entity_base_repository.get_by_id.return_value = entity_base

        # Events up to chapter 5 (repository should filter)
        events = [
            {
                "event_id": "event-1",
                "novel_id": "novel-1",
                "chapter_number": 3,
                "event_summary": "升级",
                "mutations": [{"attribute": "等级", "action": "add", "value": "5"}],
                "timestamp_ts": "2026-04-05T01:00:00"
            },
            {
                "event_id": "event-2",
                "novel_id": "novel-1",
                "chapter_number": 5,
                "event_summary": "再次升级",
                "mutations": [{"attribute": "等级", "action": "add", "value": "10"}],
                "timestamp_ts": "2026-04-05T02:00:00"
            }
        ]
        mock_narrative_event_repository.list_up_to_chapter.return_value = events

        # Act: Query state at chapter 5
        state = service.get_state("entity-1", 5)

        # Assert: Repository called with correct chapter filter
        mock_narrative_event_repository.list_up_to_chapter.assert_called_once_with("novel-1", 5)

        # Assert: Both events should be replayed
        assert state["等级"] == "10"
