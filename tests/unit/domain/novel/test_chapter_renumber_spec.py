from domain.novel.value_objects.chapter_renumber_spec import ChapterRenumberSpec


def test_shift_gt_deleted_decrements():
    spec = ChapterRenumberSpec(novel_id="n1", deleted_chapter_number=2)
    assert spec.shift_chapter_ref(3) == 2
    assert spec.shift_chapter_ref(1) == 1


def test_shift_eq_deleted_collapses():
    spec = ChapterRenumberSpec(novel_id="n1", deleted_chapter_number=2)
    assert spec.shift_chapter_ref(2) == 1


def test_shift_optional_none():
    spec = ChapterRenumberSpec(novel_id="n1", deleted_chapter_number=1)
    assert spec.shift_optional_chapter_ref(None) is None
