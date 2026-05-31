"""StoryPipeline generation prompt helper tests — two-stage (script → prose)."""
from engine.pipeline.context import PipelineContext
from engine.pipeline.generation_prompt_builder import (
    DEFAULT_PIPELINE_SYSTEM_PROMPT,
    SCRIPT_SYSTEM_PROMPT,
    build_generation_prompt,
    make_prompt,
    make_script_prompt,
)


def test_build_generation_prompt_orders_script_outline_voice_context():
    ctx = PipelineContext(
        script="【场景设定】档案室\n【动作设计】推门闯入",
        outline="本章大纲：主角夺回证据",
        voice_anchors="【声线锚点】冷峻、克制",
        context_text="核心上下文：守卫已布防",
    )

    prompt = build_generation_prompt(ctx)

    script_pos = prompt.index("【导演剧本")
    outline_pos = prompt.index("【章节大纲")
    voice_pos = prompt.index("【声线锚点")
    ctx_pos = prompt.index("【参考背景")

    assert script_pos < outline_pos < voice_pos < ctx_pos
    assert "推门闯入" in prompt
    assert "主角夺回证据" in prompt
    assert "核心上下文" in prompt


def test_build_generation_prompt_skips_missing_sections():
    ctx = PipelineContext(script="【场景】只有剧本")

    prompt = build_generation_prompt(ctx)

    assert "【导演剧本" in prompt
    assert "【章节大纲" not in prompt
    assert "【声线锚点" not in prompt
    assert "【参考背景" not in prompt


def test_build_generation_prompt_empty_context_returns_empty_string():
    assert build_generation_prompt(PipelineContext()) == ""


def test_make_prompt_returns_domain_prompt_with_prose_system():
    prompt = make_prompt("正文要求")

    assert getattr(prompt, "user", None) == "正文要求"
    assert getattr(prompt, "system", "") == DEFAULT_PIPELINE_SYSTEM_PROMPT


def test_make_script_prompt_returns_domain_prompt_with_script_system():
    prompt = make_script_prompt("剧本要求")

    assert getattr(prompt, "user", None) == "剧本要求"
    assert getattr(prompt, "system", "") == SCRIPT_SYSTEM_PROMPT
