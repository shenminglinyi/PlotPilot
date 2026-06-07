"""Lifecycle sandglass helpers for context allocation."""
from __future__ import annotations

import logging
from typing import Any, Dict

from engine.core.entities.story import StoryPhase

logger = logging.getLogger(__name__)

DEFAULT_PHASE_THRESHOLDS: Dict[str, float] = {
    "opening": 0.25,
    "development": 0.75,
    "convergence": 0.90,
    "finale": 1.01,
}


def estimate_total_chapters(story_node_repository: Any, novel_id: str) -> int:
    """Estimate target chapter count from the story structure."""
    if not story_node_repository:
        return 100

    try:
        nodes = story_node_repository.get_by_novel_sync(novel_id)
        if not nodes:
            return 100

        part_nodes = [node for node in nodes if node.node_type.value == "part"]
        for part in part_nodes:
            if part.chapter_end and part.chapter_end > 0:
                return part.chapter_end

        total_suggested = sum(
            (part.suggested_chapter_count or 0)
            for part in part_nodes
            if part.suggested_chapter_count
        )
        if total_suggested > 0:
            return total_suggested

        chapter_nodes = [node for node in nodes if node.node_type.value == "chapter"]
        if chapter_nodes:
            max_chapter = max(node.number for node in chapter_nodes)
            if max_chapter > 0:
                return max(int(max_chapter * 1.2), max_chapter + 10)
    except Exception as exc:
        logger.warning("估算总章节数失败: %s", exc)

    return 100


def load_phase_thresholds(
    registry: Any,
    prompt_id: str,
    defaults: Dict[str, float] | None = None,
) -> Dict[str, float]:
    """Load configurable phase thresholds from PromptRegistry."""
    base = dict(defaults or DEFAULT_PHASE_THRESHOLDS)
    try:
        custom = registry.get_field(prompt_id, "_phase_thresholds", None)
        if isinstance(custom, dict):
            for key in ["opening", "development", "convergence", "finale"]:
                if key not in custom:
                    continue
                value = float(custom[key])
                if 0.0 <= value <= 1.01:
                    base[key] = value
            logger.info("沙漏阶段阈值已从配置加载: %s", base)
    except Exception as exc:
        logger.debug("加载沙漏阶段阈值失败，使用默认值: %s", exc)
    return base


def classify_phase(progress: float, thresholds: Dict[str, float]) -> StoryPhase:
    """Classify lifecycle phase from global progress."""
    if progress >= thresholds.get("convergence", 0.90):
        if progress >= thresholds.get("finale", 1.01):
            return StoryPhase.FINALE
        return StoryPhase.CONVERGENCE
    if progress >= thresholds.get("opening", 0.25):
        return StoryPhase.DEVELOPMENT
    return StoryPhase.OPENING


def get_phase_directives(registry: Any, prompt_id: str) -> Dict[StoryPhase, str]:
    """Load lifecycle phase directives from PromptRegistry."""
    raw = registry.get_directives_dict(prompt_id, directives_key="_directives")
    if not raw:
        logger.warning("沙漏阶段指令未找到 (id=%s)，使用空指令", prompt_id)
        return {}

    result: Dict[StoryPhase, str] = {}
    for key, value in raw.items():
        try:
            result[StoryPhase[key]] = str(value)
        except KeyError:
            logger.debug("未知阶段 key=%s，跳过", key)
    return result


def build_lifecycle_directive(
    *,
    story_node_repository: Any,
    novel_id: str,
    chapter_number: int,
    thresholds: Dict[str, float],
    registry: Any,
    prompt_id: str,
) -> str:
    """Render the lifecycle behavior directive block."""
    total = estimate_total_chapters(story_node_repository, novel_id)
    progress = chapter_number / max(total, 1)
    phase = classify_phase(progress, thresholds)

    directives = get_phase_directives(registry, prompt_id)
    directive = f"{directives.get(phase, '')}\n\n"
    directive += "——\n"
    directive += f"全局进度：第 {chapter_number} 章 / 约 {total} 章 ({progress:.0%})\n"
    directive += f"当前阶段：{phase.value}\n"

    if phase == StoryPhase.CONVERGENCE:
        remaining = total - chapter_number
        extra_tpl = registry.get_field(prompt_id, "_convergence_extra", "")
        directive += (
            extra_tpl.format(remaining=remaining)
            if extra_tpl
            else f"剩余约 {remaining} 章完成收束，时间紧迫。\n"
        )
    elif phase == StoryPhase.FINALE:
        remaining = total - chapter_number
        extra_tpl = registry.get_field(prompt_id, "_finale_extra", "")
        directive += (
            extra_tpl.format(remaining=remaining)
            if extra_tpl
            else f"剩余约 {remaining} 章，这是最后的冲刺。\n"
        )

    return directive
