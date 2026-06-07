from types import SimpleNamespace

from application.engine.services.recent_chapter_context import (
    build_recent_chapters_context,
    excerpt_immediate_previous_chapter,
)


def _chapter(number, title, content):
    return SimpleNamespace(number=number, title=title, content=content)


def test_previous_chapter_excerpt_uses_head_and_tail_for_long_content():
    excerpt = excerpt_immediate_previous_chapter(
        "abcdefghij",
        head_chars=3,
        tail_chars=4,
    )

    assert excerpt == "【章首略览】\nabc……\n【章末节选，供本章开头承接】\nghij"


def test_previous_chapter_excerpt_keeps_short_content_as_tail():
    excerpt = excerpt_immediate_previous_chapter(
        "abc",
        head_chars=3,
        tail_chars=4,
    )

    assert excerpt == "【章末节选，供本章开头承接】\nabc"


def test_recent_chapters_context_applies_n1_n2_and_older_policies():
    context = build_recent_chapters_context(
        [
            _chapter(7, "更早", "older chapter body"),
            _chapter(8, "上上章", "abcdefghij"),
            _chapter(9, "上一章", "klmnopqrst"),
        ],
        chapter_number=10,
        prev_head_chars=3,
        prev_tail_chars=4,
        older_head_chars=5,
    )

    assert "第 7 章：更早" in context
    assert "【章首预览】\nolder..." in context
    assert "第 8 章：上上章" in context
    assert "【章末节选，供跨章一致性参考】\nij" in context
    assert "第 9 章：上一章" in context
    assert "【章首略览】\nklm……" in context
    assert "【章末节选，供本章开头承接】\nqrst" in context


def test_recent_chapters_context_includes_current_continuation_tail():
    context = build_recent_chapters_context(
        [
            _chapter(9, "上一章", "previous"),
            _chapter(10, "当前章", "x" * 2100),
        ],
        chapter_number=10,
        current_beat_index=2,
        prev_head_chars=3,
        prev_tail_chars=4,
        older_head_chars=5,
    )

    assert "【本章已生成（断点续写上下文）】" in context
    assert "当前节拍索引: 2" in context
    assert "已生成 2100 字" in context
    assert ("x" * 2000) in context
