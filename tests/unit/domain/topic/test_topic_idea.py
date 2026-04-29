"""TopicIdea 领域模型测试。"""

import pytest

from domain.topic.entities import TopicIdea, TopicIdeaStatus


def test_topic_idea_normalizes_fields_and_lists():
    idea = TopicIdea(
        title="  测试选题  ",
        status="draft",
        selling_points=[" 爽点 ", "", "爽点", "反转"],
        market_tags=[" 玄幻 ", "玄幻", "升级"],
        score=120,
        adopted_novel_id="  ",
        development_notes={" 核心 ": "可立项"},
        evaluation={"hook": 8},
    )

    assert idea.title == "测试选题"
    assert idea.status == TopicIdeaStatus.DRAFT
    assert idea.selling_points == ["爽点", "反转"]
    assert idea.market_tags == ["玄幻", "升级"]
    assert idea.score == 100
    assert idea.adopted_novel_id is None
    assert idea.development_notes == {" 核心 ": "可立项"}
    assert idea.evaluation == {"hook": 8}


def test_topic_idea_defaults_and_safely_normalizes_report_dicts():
    idea = TopicIdea(
        title="报告字段",
        development_notes=["not", "dict"],
        evaluation="bad",
    )

    assert idea.development_notes == {}
    assert idea.evaluation == {}


def test_topic_idea_rejects_empty_title():
    with pytest.raises(ValueError, match="title"):
        TopicIdea(title="   ")


def test_update_status_clears_adopted_novel_when_not_adopted():
    idea = TopicIdea(title="测试选题")

    idea.update_status("adopted", adopted_novel_id="novel-1")
    assert idea.status == TopicIdeaStatus.ADOPTED
    assert idea.adopted_novel_id == "novel-1"

    idea.update_status("archived")
    assert idea.status == TopicIdeaStatus.ARCHIVED
    assert idea.adopted_novel_id is None
