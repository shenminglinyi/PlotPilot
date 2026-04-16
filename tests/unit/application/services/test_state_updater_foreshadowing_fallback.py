from unittest.mock import Mock

from application.analyst.services.state_updater import StateUpdater
from domain.bible.entities.bible import Bible
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.value_objects.chapter_state import ChapterState
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel,
)
from domain.novel.value_objects.novel_id import NovelId


def test_update_from_chapter_resolves_foreshadowing_by_description():
    novel_id = NovelId("novel-1")
    bible_repository = Mock()
    foreshadowing_repository = Mock()
    bible_repository.get_by_novel_id.return_value = Bible(id="bible-1", novel_id=novel_id)

    registry = ForeshadowingRegistry(id="fr-1", novel_id=novel_id)
    registry.register(
        Foreshadowing(
            id="f-1",
            planted_in_chapter=3,
            description="衣物被更换",
            importance=ImportanceLevel.MEDIUM,
            status=ForeshadowingStatus.PLANTED,
        )
    )
    foreshadowing_repository.get_by_novel_id.return_value = registry

    updater = StateUpdater(
        bible_repository=bible_repository,
        foreshadowing_repository=foreshadowing_repository,
    )

    chapter_state = ChapterState(
        new_characters=[],
        character_actions=[],
        relationship_changes=[],
        foreshadowing_planted=[],
        foreshadowing_resolved=[{"foreshadowing_id": "衣物被更换", "chapter": 5}],
        events=[],
    )

    updater.update_from_chapter("novel-1", 5, chapter_state)

    saved_registry = foreshadowing_repository.save.call_args[0][0]
    resolved = saved_registry.get_by_id("f-1")
    assert resolved is not None
    assert resolved.status == ForeshadowingStatus.RESOLVED
    assert resolved.resolved_in_chapter == 5


def test_update_from_chapter_does_not_resolve_ambiguous_foreshadowing_description():
    novel_id = NovelId("novel-1")
    bible_repository = Mock()
    foreshadowing_repository = Mock()
    bible_repository.get_by_novel_id.return_value = Bible(id="bible-1", novel_id=novel_id)

    registry = ForeshadowingRegistry(id="fr-1", novel_id=novel_id)
    registry.register(
        Foreshadowing(
            id="f-1",
            planted_in_chapter=3,
            description="衣物被更换",
            importance=ImportanceLevel.MEDIUM,
            status=ForeshadowingStatus.PLANTED,
        )
    )
    registry.register(
        Foreshadowing(
            id="f-2",
            planted_in_chapter=4,
            description="衣物被更换后袖口有血",
            importance=ImportanceLevel.HIGH,
            status=ForeshadowingStatus.PLANTED,
        )
    )
    foreshadowing_repository.get_by_novel_id.return_value = registry

    updater = StateUpdater(
        bible_repository=bible_repository,
        foreshadowing_repository=foreshadowing_repository,
    )

    chapter_state = ChapterState(
        new_characters=[],
        character_actions=[],
        relationship_changes=[],
        foreshadowing_planted=[],
        foreshadowing_resolved=[{"foreshadowing_id": "衣物被更换后", "chapter": 5}],
        events=[],
    )

    updater.update_from_chapter("novel-1", 5, chapter_state)

    saved_registry = foreshadowing_repository.save.call_args[0][0]
    assert saved_registry.get_by_id("f-1").status == ForeshadowingStatus.PLANTED
    assert saved_registry.get_by_id("f-2").status == ForeshadowingStatus.PLANTED
