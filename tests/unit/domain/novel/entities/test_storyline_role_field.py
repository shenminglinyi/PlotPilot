from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_role import StorylineRole
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_type import StorylineType


def _make_storyline(**kwargs):
    defaults = dict(
        id="sl-1",
        novel_id=NovelId("novel-1"),
        storyline_type=StorylineType.MAIN_PLOT,
        status=StorylineStatus.ACTIVE,
        estimated_chapter_start=1,
        estimated_chapter_end=80,
    )
    defaults.update(kwargs)
    return Storyline(**defaults)


def test_storyline_default_role():
    sl = _make_storyline()
    assert sl.role == StorylineRole.MAIN


def test_storyline_sub_role():
    sl = _make_storyline(role=StorylineRole.SUB)
    assert sl.role == StorylineRole.SUB


def test_storyline_parent_id_default_none():
    sl = _make_storyline()
    assert sl.parent_id is None


def test_storyline_chapter_weight_default():
    sl = _make_storyline()
    assert sl.chapter_weight == 1.0
