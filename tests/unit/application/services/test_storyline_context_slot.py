"""Tests for ContextBudgetAllocator._build_storyline_slot() — no DB needed."""
from unittest.mock import MagicMock
from domain.novel.entities.storyline import Storyline
from domain.novel.entities.confluence_point import ConfluencePoint
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_role import StorylineRole
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_type import StorylineType
from application.engine.services.context_budget_allocator import ContextBudgetAllocator


def _sl(id, role, start, end, parent_id=None, weight=1.0, summary=""):
    return Storyline(
        id=id, novel_id=NovelId("n1"),
        storyline_type=StorylineType.MAIN_PLOT,
        status=StorylineStatus.ACTIVE,
        estimated_chapter_start=start, estimated_chapter_end=end,
        role=role, parent_id=parent_id, chapter_weight=weight,
        progress_summary=summary,
    )


def _cp(source_id, target_chapter, merge_type="absorb", summary="汇流发生", guards=None, hint=""):
    return ConfluencePoint(
        id=f"cp-{source_id}", novel_id="n1",
        source_storyline_id=source_id, target_storyline_id="sl-main",
        target_chapter=target_chapter, merge_type=merge_type,
        context_summary=summary, pre_reveal_hint=hint,
        behavior_guards=guards or [],
    )


def _make_allocator(storylines, confluences):
    storyline_repo = MagicMock()
    storyline_repo.get_by_novel_id.return_value = storylines
    confluence_repo = MagicMock()
    confluence_repo.get_by_novel_id.return_value = confluences
    alloc = ContextBudgetAllocator.__new__(ContextBudgetAllocator)
    alloc.storyline_repo = storyline_repo
    alloc.confluence_repo = confluence_repo
    return alloc


def test_inactive_storyline_not_in_slot():
    """Storyline outside chapter range is not injected."""
    sl_inactive = _sl("sl-1", StorylineRole.SUB, start=50, end=80)
    alloc = _make_allocator([sl_inactive], [])
    result = alloc._build_storyline_slot("n1", chapter_number=10)
    assert result == ""


def test_low_weight_storyline_skipped():
    """chapter_weight < 0.05 storylines are skipped."""
    sl_low = _sl("sl-2", StorylineRole.SUB, start=1, end=80, weight=0.01)
    alloc = _make_allocator([sl_low], [])
    result = alloc._build_storyline_slot("n1", chapter_number=10)
    assert result == ""


def test_t0_near_confluence_contains_summary():
    """Within 2 chapters of confluence, full context_summary appears."""
    sl_sub = _sl("sl-sub", StorylineRole.SUB, start=1, end=40, parent_id="sl-main")
    cp = _cp("sl-sub", target_chapter=40, summary="苏蔓保护顾言之，暴露情报来源")
    alloc = _make_allocator([sl_sub], [cp])
    result = alloc._build_storyline_slot("n1", chapter_number=39)
    assert "苏蔓保护顾言之" in result


def test_dark_line_pre_reveal_hint_shown_before_reveal():
    """Dark line before reveal only shows pre_reveal_hint, not context_summary."""
    sl_dark = _sl("sl-dark", StorylineRole.DARK, start=1, end=80)
    cp = _cp("sl-dark", target_chapter=75, merge_type="reveal",
             summary="幕后黑手现身",
             hint="存在一条隐藏的因果链，保持以下禁忌",
             guards=["禁止任何角色提及幕后人"])
    alloc = _make_allocator([sl_dark], [cp])
    result = alloc._build_storyline_slot("n1", chapter_number=10)
    assert "幕后黑手现身" not in result
    assert "存在一条隐藏的因果链" in result
    assert "禁止任何角色提及幕后人" in result


def test_active_main_line_appears():
    """Active main storyline appears in output."""
    sl_main = _sl("sl-main", StorylineRole.MAIN, start=1, end=80, summary="顾言之复仇进行中")
    alloc = _make_allocator([sl_main], [])
    result = alloc._build_storyline_slot("n1", chapter_number=10)
    assert result != ""
    assert "主线" in result
