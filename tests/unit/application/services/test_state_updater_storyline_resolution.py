"""Test storyline name resolution and auto-creation logic in StateUpdater."""
import pytest
from unittest.mock import Mock
from application.analyst.services.state_updater import StateUpdater
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.repositories.storyline_repository import StorylineRepository
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository


class TestStorylineResolution:
    """Test _resolve_storyline_by_name fuzzy matching logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.storyline_repository = Mock(spec=StorylineRepository)
        self.updater = StateUpdater(
            bible_repository=Mock(spec=BibleRepository),
            foreshadowing_repository=Mock(spec=ForeshadowingRepository),
            storyline_repository=self.storyline_repository,
        )
        self.novel_id = NovelId("novel-test")

    def _make_storyline(self, id: str, name: str) -> Storyline:
        return Storyline(
            id=id,
            novel_id=self.novel_id,
            storyline_type=StorylineType.GROWTH,
            status=StorylineStatus.ACTIVE,
            estimated_chapter_start=1,
            estimated_chapter_end=50,
            name=name,
        )

    def test_exact_match(self):
        """Exact name match should return the storyline."""
        sl = self._make_storyline("sl-1", "盲眼老人的阵盘")
        self.storyline_repository.get_by_novel_id.return_value = [sl]

        result = self.updater._resolve_storyline_by_name(self.novel_id, "盲眼老人的阵盘")
        assert result is not None
        assert result.id == "sl-1"

    def test_normalized_match(self):
        """Normalized match (case/whitespace insensitive) should work."""
        sl = self._make_storyline("sl-2", "收割教廷阴谋")
        self.storyline_repository.get_by_novel_id.return_value = [sl]

        # Different whitespace/case
        result = self.updater._resolve_storyline_by_name(self.novel_id, " 收割教廷阴谋 ")
        assert result is not None
        assert result.id == "sl-2"

    def test_substring_match_unique(self):
        """Unique substring match should return the storyline."""
        sl = self._make_storyline("sl-3", "碎片之谜")
        self.storyline_repository.get_by_novel_id.return_value = [sl]

        # LLM might extract a partial name
        result = self.updater._resolve_storyline_by_name(self.novel_id, "碎片")
        assert result is not None
        assert result.id == "sl-3"

    def test_substring_match_ambiguous_returns_none(self):
        """Ambiguous substring match should return None."""
        sl1 = self._make_storyline("sl-4", "碎片之谜")
        sl2 = self._make_storyline("sl-5", "碎片的秘密")
        self.storyline_repository.get_by_novel_id.return_value = [sl1, sl2]

        result = self.updater._resolve_storyline_by_name(self.novel_id, "碎片")
        assert result is None

    def test_no_match_returns_none(self):
        """No match should return None."""
        sl = self._make_storyline("sl-6", "主线剧情")
        self.storyline_repository.get_by_novel_id.return_value = [sl]

        result = self.updater._resolve_storyline_by_name(self.novel_id, "完全无关的名称")
        assert result is None

    def test_empty_storyline_list_returns_none(self):
        """Empty storyline list should return None."""
        self.storyline_repository.get_by_novel_id.return_value = []

        result = self.updater._resolve_storyline_by_name(self.novel_id, "任何名称")
        assert result is None
