from types import SimpleNamespace

from application.world.services.chapter_narrative_sync import (
    _match_storyline_for_progress_item,
)


def _storyline(name, description="", last_active_chapter=0, start=1):
    return SimpleNamespace(
        name=name,
        description=description,
        last_active_chapter=last_active_chapter,
        estimated_chapter_start=start,
    )


def test_storyline_matching_merges_synonymous_case_labels():
    existing = [
        _storyline("禁器指控危机", "执法堂以私制禁器罪名传召主角", 4, 4),
        _storyline("黑市人脉", "与银面具人建立交易关系", 3, 3),
    ]

    matched = _match_storyline_for_progress_item(
        existing,
        line_type="主线",
        arc_label="禁器构陷案",
        description="执法堂公审，主角被控私制禁器并被谷梁卿羽构陷",
    )

    assert matched is existing[0]


def test_storyline_matching_merges_teacher_relic_variants():
    existing = [
        _storyline("师尊遗物寻踪", "黑市神秘人提示师尊本命飞剑藏于昆仑山脉", 8, 8),
    ]

    matched = _match_storyline_for_progress_item(
        existing,
        line_type="主线",
        arc_label="师尊遗产寻踪",
        description="银面具人传音告知师尊遗产位置，主角准备前往昆仑",
    )

    assert matched is existing[0]
