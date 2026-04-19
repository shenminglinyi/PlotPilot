from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.entities.subtext_ledger_entry import SubtextLedgerEntry
from domain.novel.value_objects.chapter_renumber_spec import ChapterRenumberSpec
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel,
)
from domain.novel.value_objects.novel_id import NovelId


def test_apply_renumber_shifts_foreshadow_and_subtext():
    reg = ForeshadowingRegistry(id="fr-1", novel_id=NovelId("n1"))
    reg.register(
        Foreshadowing(
            id="f1",
            planted_in_chapter=3,
            description="x",
            importance=ImportanceLevel.MEDIUM,
            status=ForeshadowingStatus.PLANTED,
            suggested_resolve_chapter=4,
        )
    )
    reg.add_subtext_entry(
        SubtextLedgerEntry(
            id="s1",
            chapter=3,
            character_id="c1",
            question="q",
            status="pending",
        )
    )
    spec = ChapterRenumberSpec(novel_id="n1", deleted_chapter_number=2)
    reg.apply_chapter_renumber_after_chapter_deleted(spec)

    f = reg.foreshadowings[0]
    assert f.planted_in_chapter == 2
    assert f.suggested_resolve_chapter == 3
    assert reg.subtext_entries[0].chapter == 2
