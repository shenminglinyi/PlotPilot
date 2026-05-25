"""Generation prompt helpers for StoryPipeline."""
from __future__ import annotations

from typing import Any, List

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


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def build_director_contract(beat: Any) -> str:
    """Render the beat-level delivery contract (action / conflict / delta only)."""
    lines: List[str] = []
    for label, attr in (
        ("必须写出的可见行为", "visible_action"),
        ("冲突/阻碍", "conflict"),
        ("本拍局面变化", "delta"),
        ("交给下一拍", "handoff_to_next"),
    ):
        value = getattr(beat, attr, "") or ""
        if str(value).strip():
            lines.append(f"{label}：{value}")
    must_include = _string_list(getattr(beat, "must_include", None))
    must_not = _string_list(getattr(beat, "must_not_include", None))
    if must_include:
        lines.append("必须包含：" + "；".join(must_include))
    if must_not:
        lines.append("不得违背：" + "；".join(must_not))
    if not lines:
        return ""
    return (
        "━━━ 本拍唯一任务（优先于背景设定；只交付下面这一拍的变化，禁止复述世界观）━━━\n"
        + "\n".join(lines)
    )


def build_generation_prompt(ctx: PipelineContext, beat: Any, beat_index: int) -> str:
    """Build the user-side prompt for one beat.

    Beat task and director contract come first; encyclopedic context is reference-only.
    """
    parts: List[str] = []
    beat_desc = getattr(beat, "description", str(beat))
    beat_focus = getattr(beat, "focus", "mixed")
    subbeats = getattr(beat, "subbeat_descriptions", None) or []
    label = "当前写作包" if len(subbeats) > 1 else "当前节拍"
    parts.append(f"【{label} {beat_index + 1}/{len(ctx.beats)}】{beat_desc}（焦点：{beat_focus}）")

    director_contract = build_director_contract(beat)
    if director_contract:
        parts.append(director_contract)

    card_block = getattr(beat, "card_prompt_block", "")
    if card_block:
        parts.append(card_block)

    if ctx.outline:
        parts.append(f"【章节大纲（只取与本拍相关的一句，勿整段复述）】\n{ctx.outline}")

    if ctx.voice_anchors:
        parts.append(ctx.voice_anchors)

    if ctx.context_text:
        parts.append(
            "【参考背景（勿复述设定与已写情节，只服务本拍动作）】\n" + ctx.context_text
        )

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
    "build_director_contract",
    "build_generation_prompt",
    "make_prompt",
]
