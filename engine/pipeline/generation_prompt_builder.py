"""Generation prompt helpers for StoryPipeline."""
from __future__ import annotations

from typing import Any

from engine.pipeline.context import PipelineContext

DEFAULT_PIPELINE_SYSTEM_PROMPT = (
    "你是一位正在埋头创作的中文网络小说作者，此刻的任务只有一个：按给定的节拍简报写出正文段落。\n\n"
    "铁律（违反即判定为输出失败）：\n"
    "1. 只输出故事正文，不得输出任何分析、点评、建议、问题、说明或思维过程。\n"
    "2. 不得重复、引用或解释节拍简报里的任何指令文字。\n"
    "3. 不得以「作为一名AI」、「根据你的设定」、「我注意到」、「建议」等词语开头或出现在正文中。\n"
    "4. 用白描手法写——情绪通过动作与感官细节体现，不写'他感到愤怒'，写'他端起杯子又放下'。\n"
    "5. 下笔即是正文第一个字，收笔即是正文最后一个字，中间没有标题、序号、换行空白。"
)


def build_generation_prompt(ctx: PipelineContext, beat: Any, beat_index: int) -> str:
    """Build the user-side prompt for one beat."""
    parts = []
    if ctx.context_text:
        parts.append(ctx.context_text)
    if ctx.voice_anchors:
        parts.append(ctx.voice_anchors)
    if ctx.outline:
        parts.append(f"【章节大纲】\n{ctx.outline}")
    beat_desc = getattr(beat, "description", str(beat))
    beat_focus = getattr(beat, "focus", "mixed")
    parts.append(f"【当前节拍 {beat_index + 1}/{len(ctx.beats)}】{beat_desc}（焦点：{beat_focus}）")
    card_block = getattr(beat, "card_prompt_block", "")
    if card_block:
        parts.append(card_block)
    return "\n\n".join(parts)


def make_prompt(text: str) -> Any:
    """Convert user prompt text to the domain Prompt value object when available."""
    try:
        from domain.ai.value_objects.prompt import Prompt

        return Prompt(system=DEFAULT_PIPELINE_SYSTEM_PROMPT, user=text)
    except ImportError:
        return text


__all__ = [
    "DEFAULT_PIPELINE_SYSTEM_PROMPT",
    "build_generation_prompt",
    "make_prompt",
]
