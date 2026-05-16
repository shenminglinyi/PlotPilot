from domain.novel.entities.confluence_point import ConfluencePoint


def test_confluence_point_creation():
    cp = ConfluencePoint(
        id="cp-1",
        novel_id="novel-1",
        source_storyline_id="sl-sub-1",
        target_storyline_id="sl-main-1",
        target_chapter=38,
        merge_type="absorb",
        context_summary="苏蔓选择保护顾言之，暴露自己的情报来源",
        pre_reveal_hint="",
        behavior_guards=[],
    )
    assert cp.target_chapter == 38
    assert cp.resolved is False
    assert cp.merge_type == "absorb"


def test_confluence_point_reveal_type():
    cp = ConfluencePoint(
        id="cp-2",
        novel_id="novel-1",
        source_storyline_id="sl-dark-1",
        target_storyline_id="sl-main-1",
        target_chapter=75,
        merge_type="reveal",
        context_summary="幕后黑手正式现身",
        pre_reveal_hint="存在一条隐藏的因果链正在运行，不要让任何角色表现出对此的知晓",
        behavior_guards=["禁止让林警官表现出对顾言之真实身份有任何怀疑"],
    )
    assert cp.behavior_guards[0].startswith("禁止")
    assert cp.pre_reveal_hint != ""


def test_confluence_point_invalid_merge_type():
    import pytest
    with pytest.raises(ValueError):
        ConfluencePoint(
            id="cp-3", novel_id="n1",
            source_storyline_id="sl-1", target_storyline_id="sl-main",
            target_chapter=10, merge_type="invalid_type",
            context_summary="", pre_reveal_hint="", behavior_guards=[],
        )
