"""节拍上下文抽取器测试。"""

from application.workflows.beat_context_extractor import (
    extract_beat_tail_anchor,
    extract_core_event,
    extract_paragraph_participants,
)


def test_extract_core_event_prefers_conflict_over_plain_opening():
    paragraph = (
        "雨已经下了很久，街口的灯一盏盏暗下去。"
        "林舟忽然发现账本少了一页，他抓住门把，质问对面的人为什么隐瞒。"
        "对方没有回答，只把钥匙推到桌边。"
    )

    event = extract_core_event(paragraph)

    assert "账本少了一页" in event
    assert "质问" in event


def test_extract_paragraph_participants_from_dialogue_signals():
    paragraph = "林舟低声问：“你到底看见了什么？”顾眠回答：“我只看见钥匙。”"

    assert extract_paragraph_participants(paragraph) == "林舟、顾眠"


def test_extract_beat_tail_anchor_detects_mood_and_last_moment():
    text = "门外的脚步声越来越近。林舟屏息握紧钥匙，冷汗从指缝里滑下来。"

    anchor = extract_beat_tail_anchor(text)

    assert anchor.tail_state in {"叙述中", "动作中"}
    assert anchor.mood_tone == "紧张"
    assert "钥匙" in anchor.last_moment
