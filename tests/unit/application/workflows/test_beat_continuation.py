"""节拍续写：已写正文截断与注入格式。"""

from application.workflows.beat_continuation import format_prior_draft_for_prompt


def test_empty_returns_empty():
    assert format_prior_draft_for_prompt("") == ""
    assert format_prior_draft_for_prompt("   ") == ""


def test_short_text_unchanged():
    assert format_prior_draft_for_prompt("已写一段") == "已写一段"


def test_long_text_keeps_tail_with_notice():
    body = "x" * 20_000
    out = format_prior_draft_for_prompt(body)
    assert "省略" in out
    assert out.endswith("x" * 14_000)
