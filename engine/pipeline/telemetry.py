"""StoryPipeline 可观测性：十步管线波次标识（后端 / UI 对齐单源）。

与 BaseStoryPipeline.run_chapter 步骤顺序一致，index 从 1 起。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

STORY_PIPELINE_WAVE_TOTAL = 10

# (index, id, label)
_STORY_PIPELINE_WAVES: Tuple[Tuple[int, str, str], ...] = (
    (1, "find_chapter", "章节定位"),
    (2, "build_context", "组装上下文"),
    (3, "magnify_beats", "节拍拆分"),
    (4, "generate", "正文生成"),
    (5, "validate_policy", "策略校验"),
    (6, "persist_chapter", "章节落盘"),
    (7, "voice_audit", "文风审计"),
    (8, "aftermath", "章后管线"),
    (9, "score_tension", "张力打分"),
    (10, "finalize", "收尾"),
)


def story_pipeline_wave_meta(wave_index: int) -> Optional[Dict[str, Any]]:
    """返回 story_pipeline_wave_id / story_pipeline_wave_label 等，index 无效则 None。"""
    if wave_index < 1 or wave_index > STORY_PIPELINE_WAVE_TOTAL:
        return None
    idx, wave_id, label = _STORY_PIPELINE_WAVES[wave_index - 1]
    return {
        "story_pipeline_wave_index": idx,
        "story_pipeline_wave_total": STORY_PIPELINE_WAVE_TOTAL,
        "story_pipeline_wave_id": wave_id,
        "story_pipeline_wave_label": label,
    }


def story_pipeline_waves_manifest() -> List[Dict[str, Any]]:
    """供可选 API/debug 枚举用。"""
    return [
        {"index": idx, "id": wid, "label": lbl}
        for idx, wid, lbl in _STORY_PIPELINE_WAVES
    ]
