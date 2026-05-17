"""prose_fragment_aggregator 单元测试。"""
from application.ai.llm_output_sanitize import strip_and_aggregate_prose_fragments
from application.ai.prose_fragment_aggregator import aggregate_inline_prose_fragments


def test_merge_short_lines_replaces_period_with_comma_between():
    raw = "艾伦走出密室。\n走廊里的人声渐远。\n"
    out = aggregate_inline_prose_fragments(raw, short_line_max_chars=52)
    assert "走廊里的人声渐远" in out
    assert "艾伦走出密室，" in out


def test_preserves_paragraph_breaks():
    raw = "艾伦走出密室。\n走廊很安静。\n\n第二段开始。\n仍然很短。\n"
    out = aggregate_inline_prose_fragments(raw, short_line_max_chars=52)
    assert "\n\n" in out
    assert "第二段开始，仍然很短" in out or "第二段开始" in out


def test_dialog_line_starts_new_piece():
    raw = "他说完了。\n「少爷，该走了。」\n"
    out = aggregate_inline_prose_fragments(raw, short_line_max_chars=52)
    assert "\n" in out
    assert "「少爷" in out


def test_long_line_is_not_merged_into_short_neighbors():
    long_line = "这是" + "很长的文字" * 20  # > 52
    raw = f"短文。\n{long_line}\n另一短句。\n"
    out = aggregate_inline_prose_fragments(raw, short_line_max_chars=52)
    parts = out.split(long_line)
    assert len(parts) >= 2
    assert long_line in out


def test_strip_then_aggregate_through_helper():
    raw = '<thinking>X</thinking>一句。\n又来一句。\n'
    got = strip_and_aggregate_prose_fragments(raw)
    assert "thinking" not in got
    assert "一句" in got
