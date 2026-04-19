"""ContextBudgetAllocator：紧邻上一章章末承接摘录。"""

from application.engine.services.context_budget_allocator import ContextBudgetAllocator


def test_excerpt_empty():
    alloc = ContextBudgetAllocator()
    assert alloc._excerpt_immediate_previous_chapter("") == ""
    assert alloc._excerpt_immediate_previous_chapter("   ") == ""


def test_excerpt_short_full_in_tail_block():
    alloc = ContextBudgetAllocator()
    text = "x" * 800
    out = alloc._excerpt_immediate_previous_chapter(text)
    assert "章末节选，供本章开头承接" in out
    assert "章首略览" not in out
    assert text in out


def test_excerpt_long_head_and_tail():
    alloc = ContextBudgetAllocator()
    text = "A" * 250 + "M" * 500 + "Z" * 1200
    out = alloc._excerpt_immediate_previous_chapter(text)
    assert "章首略览" in out
    assert "章末节选，供本章开头承接" in out
    assert out.endswith("Z" * 1200)
    assert "A" * 250 in out
