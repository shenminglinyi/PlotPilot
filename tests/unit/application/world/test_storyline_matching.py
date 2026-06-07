from types import SimpleNamespace

from application.world.services.chapter_narrative_sync import (
    _match_storyline_for_progress_item,
)
from application.world.services.storyline_normalization import (
    get_storyline_normalization_profile,
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
        _storyline("地下交易人脉", "与银面具人建立交易关系", 3, 3),
    ]

    matched = _match_storyline_for_progress_item(
        existing,
        line_type="主线",
        arc_label="禁器构陷案",
        description="执法堂公审，主角被控私制禁器并被谷梁卿羽构陷",
    )

    assert matched is existing[0]


def test_storyline_normalization_profile_is_loaded_from_config():
    profile = get_storyline_normalization_profile()

    assert "禁器" in profile.alias_words
    assert "冤案" in profile.distinctive_tokens
    assert profile.replacements["禁器构陷"] == "禁器案"


def test_storyline_matching_merges_teacher_relic_variants():
    existing = [
        _storyline("师尊遗物寻踪", "地下交易联络人提示师尊本命飞剑藏于昆仑山脉", 8, 8),
    ]

    matched = _match_storyline_for_progress_item(
        existing,
        line_type="主线",
        arc_label="师尊遗产寻踪",
        description="银面具人传音告知师尊遗产位置，主角准备前往昆仑",
    )

    assert matched is existing[0]


def test_storyline_matching_merges_underground_trade_variants():
    existing = [
        _storyline("地下交易势力接触", "与神秘面具人建立初步合作关系，打开地下交易渠道", 9, 3),
    ]

    matched = _match_storyline_for_progress_item(
        existing,
        line_type="主线",
        arc_label="地下交易拍卖危机",
        description="芦沉舟进入地下交易内层拍卖场，见证人口交易并与银面具修士合作",
    )

    assert matched is existing[0]


def test_storyline_matching_merges_identity_variants():
    existing = [
        _storyline("身份之谜", "芦沉舟掌握失传绝技，身份疑云加深", 13, 6),
    ]

    matched = _match_storyline_for_progress_item(
        existing,
        line_type="主线",
        arc_label="身份危机",
        description="银面具修士识破其与十年前旧案有关，身份面临暴露风险",
    )

    assert matched is existing[0]
