"""Generation prompt helpers for StoryPipeline — two-stage (script → prose)."""
from __future__ import annotations

from typing import Any

from engine.pipeline.context import PipelineContext

DEFAULT_PIPELINE_SYSTEM_PROMPT = (
    "你是一位正在埋头创作的中文网络小说作者，此刻的任务只有一个：按给定的导演剧本写出正文。\n\n"
    "铁律（违反即判定为输出失败）：\n"
    "1. 只输出故事正文，不得输出任何分析、点评、建议、问题、说明或思维过程。\n"
    "2. 不得重复、引用或解释剧本里的任何指令文字。\n"
    "3. 不得以「作为一名AI」、「根据你的设定」、「我注意到」、「建议」等词语开头或出现在正文中。\n"
    "4. 用白描手法写——情绪通过动作与感官细节体现，不写'他感到愤怒'，写'他端起杯子又放下'。\n"
    "5. 下笔即是正文第一个字，收笔即是正文最后一个字，中间没有标题、序号、换行空白。"
)

SCRIPT_SYSTEM_PROMPT = (
    "你是一位资深小说导演。你的任务是为一个章节撰写六模块导演剧本，"
    "包含：场景设定、角色出场、对话要点、动作设计、情绪曲线、节奏控制。"
    "只输出导演剧本，不要写正文。"
)


def build_generation_prompt(ctx: PipelineContext) -> str:
    """Build the prose-generation prompt from the director script.

    The script (ctx.script) is the primary input; context text is reference-only.
    """
    parts: list[str] = []

    if ctx.script:
        parts.append(f"【导演剧本（按此剧本撰写正文）】\n{ctx.script}")

    if ctx.outline:
        parts.append(f"【章节大纲（参考，勿整段复述）】\n{ctx.outline}")

    if ctx.voice_anchors:
        parts.append(ctx.voice_anchors)

    if ctx.context_text:
        parts.append(
            "【参考背景（勿复述设定与已写情节，只服务当前写作）】\n" + ctx.context_text
        )

    return "\n\n".join(parts)


def make_prompt(text: str) -> Any:
    """Convert user prompt text to the domain Prompt value object when available."""
    try:
        from domain.ai.value_objects.prompt import Prompt

        return Prompt(system=DEFAULT_PIPELINE_SYSTEM_PROMPT, user=text)
    except ImportError:
        return text


def make_script_prompt(text: str) -> Any:
    """Convert script-generation prompt text to the domain Prompt value object."""
    try:
        from domain.ai.value_objects.prompt import Prompt

        return Prompt(system=SCRIPT_SYSTEM_PROMPT, user=text)
    except ImportError:
        return text


__all__ = [
    "DEFAULT_PIPELINE_SYSTEM_PROMPT",
    "SCRIPT_SYSTEM_PROMPT",
    "build_generation_prompt",
    "make_prompt",
    "make_script_prompt",
]
