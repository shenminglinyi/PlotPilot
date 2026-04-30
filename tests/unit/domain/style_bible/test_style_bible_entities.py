"""Style Bible 领域模型测试。"""

import pytest

from domain.style_bible.entities import (
    StyleProfile,
    StyleSample,
    StyleTechniqueCard,
)


def test_style_sample_normalizes_content_and_counts_chars():
    sample = StyleSample(
        title="  第一章样本  ",
        content="  林晚推开门。\n\n“你来了？”  ",
        source_type=" reference ",
        genre="  都市  ",
        scene_type=" 对话 ",
        pov=" 第三人称 ",
        allowed_for_generation=True,
        novel_id=" novel-1 ",
        profile_id=" profile-1 ",
    )

    assert sample.title == "第一章样本"
    assert sample.content == "林晚推开门。\n\n“你来了？”"
    assert sample.source_type == "reference"
    assert sample.genre == "都市"
    assert sample.scene_type == "对话"
    assert sample.pov == "第三人称"
    assert sample.allowed_for_generation is True
    assert sample.novel_id == "novel-1"
    assert sample.profile_id == "profile-1"
    assert sample.char_count == len("林晚推开门。\n\n“你来了？”")
    assert sample.content_hash
    assert sample.id.startswith("style-sample-")


def test_style_sample_rejects_empty_content():
    with pytest.raises(ValueError, match="content"):
        StyleSample(title="空样本", content="   ")


def test_style_profile_defaults_to_active_version_one():
    profile = StyleProfile(name="  克制悬疑节奏  ")

    assert profile.name == "克制悬疑节奏"
    assert profile.status == "active"
    assert profile.version == 1
    assert profile.profile == {}
    assert profile.metrics == {}
    assert profile.rules == []
    assert profile.forbidden_patterns == []
    assert profile.id.startswith("style-profile-")


def test_style_technique_card_can_be_disabled_without_deleting():
    card = StyleTechniqueCard(
        profile_id=" profile-1 ",
        title="  对白试探  ",
        category=" dialogue ",
        scene_type=" 悬疑 ",
        rule_text="对白不能只交换寒暄。",
        prompt_instruction="每两轮对白必须释放新信息。",
    )

    card.disable()

    assert card.profile_id == "profile-1"
    assert card.title == "对白试探"
    assert card.category == "dialogue"
    assert card.scene_type == "悬疑"
    assert card.enabled is False
    assert card.id.startswith("style-card-")
