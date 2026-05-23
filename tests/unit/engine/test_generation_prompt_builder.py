"""StoryPipeline generation prompt helper tests."""
from types import SimpleNamespace

from engine.pipeline.context import PipelineContext
from engine.pipeline.generation_prompt_builder import build_generation_prompt, make_prompt


def test_build_generation_prompt_contains_context_outline_beat_and_card():
    beat = SimpleNamespace(
        description="主角夺回证据",
        focus="action",
        card_prompt_block="━━━ 节点卡\n✅ 必须写出的行为：推开门",
    )
    ctx = PipelineContext(
        context_text="核心上下文",
        voice_anchors="声线锚点",
        outline="本章大纲",
        beats=[beat],
    )

    prompt = build_generation_prompt(ctx, beat, 0)

    assert "核心上下文" in prompt
    assert "声线锚点" in prompt
    assert "【章节大纲】\n本章大纲" in prompt
    assert "【当前节拍 1/1】主角夺回证据（焦点：action）" in prompt
    assert "✅ 必须写出的行为：推开门" in prompt


def test_make_prompt_returns_domain_prompt_when_available():
    prompt = make_prompt("正文要求")

    assert getattr(prompt, "user", None) == "正文要求"
    assert getattr(prompt, "system", "")
