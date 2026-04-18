from application.core.premise_genre_world import parse_genre_world_from_premise


def test_parse_with_system_block_and_double_newline():
    text = """【系统内部·叙事结构规划】
规划目标

【类型：玄幻升级；世界观基调：修仙风】

用户梗概正文"""
    g, w = parse_genre_world_from_premise(text)
    assert g == "玄幻升级"
    assert w == "修仙风"


def test_parse_semicolon_english():
    g, w = parse_genre_world_from_premise("【类型：A;世界观基调：B】")
    assert g == "A"
    assert w == "B"
