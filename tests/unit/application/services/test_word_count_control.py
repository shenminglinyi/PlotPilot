import pytest

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from domain.ai.value_objects.prompt import Prompt
from application.engine.word_count_control import (
    check_word_count,
    generate_with_word_control,
    trim_to_target,
)


@pytest.mark.asyncio
async def test_check_word_count_within_tolerance():
    result = await check_word_count("甲" * 104, 100, tolerance=0.05)

    assert result["status"] == "ok"
    assert result["within_tolerance"] is True
    assert result["actual_word_count"] == 104


@pytest.mark.asyncio
async def test_generate_with_word_control_still_too_short_after_two_expansions():
    prompt = Prompt(system="你是小说作家", user="请生成一章内容")
    outputs = iter(["甲" * 20, "乙" * 10, "丙" * 8])

    async def llm_caller(_: Prompt) -> str:
        return next(outputs)

    result = await generate_with_word_control(prompt, 100, llm_caller)

    assert result["status"] == "too_short"
    assert result["expansion_attempts"] == 2
    assert result["fallback_used"] is True
    assert result["action"] == "expanded"


@pytest.mark.asyncio
async def test_generate_with_word_control_emits_expansion_events():
    prompt = Prompt(system="你是小说作家", user="请生成一章内容")
    outputs = iter(["甲" * 20, "乙" * 10, "丙" * 8])
    events = []

    async def llm_caller(_: Prompt) -> str:
        return next(outputs)

    async def emit_event(event):
        events.append(event)

    await generate_with_word_control(prompt, 100, llm_caller, emit_event=emit_event)

    assert len(events) == 2
    assert events[0]["word_control_step"] == "expanding"
    assert events[0]["word_control_attempt"] == 1
    assert events[1]["word_control_attempt"] == 2


@pytest.mark.asyncio
async def test_generate_with_word_control_trims_when_too_long():
    prompt = Prompt(system="你是小说作家", user="请生成一章内容")
    long_text = "第一句内容足够长。第二句继续推进剧情。第三句自然收尾。"

    async def llm_caller(_: Prompt) -> str:
        return long_text

    result = await generate_with_word_control(prompt, 12, llm_caller)

    assert result["trim_applied"] is True
    assert result["action"] == "trimmed"
    assert result["actual_word_count"] <= 12


@pytest.mark.asyncio
async def test_generate_with_word_control_emits_trim_event():
    prompt = Prompt(system="你是小说作家", user="请生成一章内容")
    events = []

    async def llm_caller(_: Prompt) -> str:
        return "第一句内容足够长。第二句继续推进剧情。第三句自然收尾。"

    async def emit_event(event):
        events.append(event)

    await generate_with_word_control(prompt, 12, llm_caller, emit_event=emit_event)

    assert len(events) == 1
    assert events[0]["word_control_step"] == "trimming"
    assert "智能裁剪" in events[0]["status_text"]


@pytest.mark.asyncio
async def test_generate_with_word_control_accepts_provider_style_llm_caller():
    prompt = Prompt(system="你是小说作家", user="请生成一章内容")
    calls = []

    async def llm_caller(current_prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        calls.append((current_prompt, config))
        return GenerationResult(
            content="甲" * 104,
            token_usage=TokenUsage(input_tokens=10, output_tokens=20),
        )

    result = await generate_with_word_control(
        prompt,
        100,
        llm_caller,
        generation_config=GenerationConfig(max_tokens=512, temperature=0.2),
    )

    assert result["status"] == "ok"
    assert len(calls) == 1
    assert isinstance(calls[0][1], GenerationConfig)
    assert calls[0][1].max_tokens == 512
    assert calls[0][1].temperature == 0.2


@pytest.mark.asyncio
async def test_trim_to_target_without_sentence_endings_falls_back_to_hard_limit():
    text = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳"

    trimmed = await trim_to_target(text, 10)

    assert trimmed == text[:10]
    assert len(trimmed) == 10
