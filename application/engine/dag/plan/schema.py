"""章级执行规划 — Pydantic Schema（与 DAG 端口 JSON 对齐，可版本演进）"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PlanDecompositionMode(StrEnum):
    """章前规划拆解来源。

    统一枚举可以避免调用链散落字符串常量，后续新增拆解器时只需扩展这里。
    """

    BEAT_SHEET = "beat_sheet"
    STRUCTURED_OUTLINE = "structured_outline"
    LLM_OUTLINE_DECOMPOSE = "llm_outline_decompose"
    RAW_OUTLINE_SINGLE = "raw_outline_single"
    EMPTY_OUTLINE = "empty_outline"
    ERROR_SINGLE_OUTLINE = "error_single_outline"


class PlanningEnvelope(BaseModel):
    """章约束信封：标识与预算，不承载叙事条文。"""

    novel_id: Optional[str] = None
    chapter_number: Optional[int] = None
    target_chapter_words: int = Field(default=2500, ge=200, le=100_000)
    source_outline_hash: Optional[str] = Field(
        default=None,
        description="可选：章纲指纹，便于缓存/幂等",
    )


class PlanAtomSpec(BaseModel):
    """最小叙事推进单元（抽象节拍规格），投影为下游 Beat / 提示词块。"""

    id: str = Field(min_length=1, max_length=64)
    intent: str = Field(
        min_length=1,
        description="该拍在叙事上要完成什么（非句法切分，而是事件/推进单元）",
    )
    weight: float = Field(default=1.0, ge=0.01, le=100.0, description="相对字数权重，供预算分配")
    source_hint: Optional[str] = Field(
        default=None,
        description="可选：引用章纲片段，仅作调试/溯源",
    )
    extensions: Dict[str, Any] = Field(default_factory=dict)


class ChapterExecutionPlan(BaseModel):
    """章前规划根文档 — DAG `chapter_plan_json` 的标准外形。"""

    schema_version: str = Field(default="plotpilot.chapter_plan.v1")
    envelope: PlanningEnvelope
    atoms: List[PlanAtomSpec] = Field(default_factory=list)
    extensions: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="如 node_type、decomposition_mode、model 等可追溯信息",
    )
