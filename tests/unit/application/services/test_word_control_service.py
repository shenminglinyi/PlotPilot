import pytest

from application.engine.services.word_control_service import WordControlService, effective_length
from domain.ai.value_objects.prompt import Prompt


def test_effective_length_ignores_whitespace():
    assert effective_length("你 好\n世界 ") == 4


def test_check_word_count_reports_status_and_range():
    svc = WordControlService(tolerance=0.15)
    result = svc.check_word_count("甲" * 2400, 3000)
    assert result.status == "too_short"
    assert result.min_allowed == 2550
    assert result.max_allowed in (3449, 3450)


def test_trim_to_target_prefers_sentence_boundary():
    svc = WordControlService()
    text = "第一句刚好结束。第二句继续展开并且很长。第三句也存在。"
    trimmed = svc.trim_to_target(text, 8)
    assert trimmed.endswith("。")
    assert effective_length(trimmed) <= 8


def test_inject_length_requirements_appends_guidance():
    svc = WordControlService()
    prompt = Prompt(system="system", user="user")
    enriched = svc.inject_length_requirements(prompt, target=3000)
    assert "目标字数：3000" in enriched.system
    assert enriched.user == "user"


@pytest.mark.asyncio
async def test_build_expansion_prompt_mentions_no_repetition():
    svc = WordControlService()
    prompt = svc.build_expansion_prompt(
        existing_text="已有内容",
        outline="大纲",
        target=3000,
        current=1800,
        attempt=1,
        max_attempts=2,
    )
    assert "严禁重复" in prompt.user
    assert "补写轮次：第 1/2 轮" in prompt.user
