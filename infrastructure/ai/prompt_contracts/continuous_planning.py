"""连续规划链路的 PromptContract 定义。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import (
    CONTINUOUS_PLANNING_NEXT_ACT,
    PLANNING_ACT,
    PLANNING_CHAPTER_PREPLAN,
    PLANNING_PRECISE_MACRO,
    PLANNING_PRECISE_REPAIR,
    PLANNING_PRECISE_VOLUME,
    PLANNING_QUICK_MACRO,
)


class PlanningQuickMacroVariables(BaseModel):
    premise: str = ""
    target_chapters: int = Field(ge=1)
    worldview: str = ""
    characters: str = ""
    genre_opening_profile: dict[str, Any] = Field(default_factory=dict)
    genre_reader_contract: dict[str, Any] = Field(default_factory=dict)
    genre_rhythm_constraints: dict[str, Any] = Field(default_factory=dict)
    planning_depth: Literal["framework", "partial", "full"] = "full"
    rec_parts: int = Field(ge=1)
    rec_volumes_per_part: int = Field(ge=1)
    rec_acts_per_volume: int = Field(ge=1)
    rec_chapters_per_act: int = Field(ge=1)
    total_recommended_acts: int = Field(ge=1)


class PlanningPreciseMacroVariables(BaseModel):
    story_context: str = ""
    target_chapters: int = Field(ge=1)
    parts: int = Field(ge=1)
    volumes_per_part: int = Field(ge=1)
    acts_per_volume: int = Field(ge=1)
    total_acts: int = Field(ge=1)
    avg_chapters_per_act: int = Field(ge=1)
    pacing_guide: str = ""
    skeleton_block: str = ""


class PlanningPreciseVolumeVariables(BaseModel):
    story_context: str = ""
    target_chapters: int = Field(ge=1)
    parts: int = Field(ge=1)
    volumes_per_part: int = Field(ge=1)
    acts_per_volume: int = Field(ge=1)
    avg_chapters_per_act: int = Field(ge=1)
    scope_block: str = ""
    example_node_id: str = "A1_1_1"


class PlanningPreciseRepairVariables(BaseModel):
    story_context: str = ""
    target_chapters: int = Field(ge=1)
    parts: int = Field(ge=1)
    volumes_per_part: int = Field(ge=1)
    acts_per_volume: int = Field(ge=1)
    avg_chapters_per_act: int = Field(ge=1)
    incomplete_acts_block: str = ""


class PlanningActVariables(BaseModel):
    context: str = Field(min_length=1)
    chapter_count: int = Field(ge=1)
    genre_label: str = ""
    world_preset: str = ""
    story_structure: str = ""
    pacing_control: str = ""
    writing_style: str = ""
    special_requirements: str = ""


class PlanningChapterPreplanVariables(BaseModel):
    chapter_number: int = Field(ge=1)
    chapter_title: str = Field(min_length=1)
    act_chapter_plan: str = Field(min_length=1)
    continuity_context: str = "暂无前3章规划大纲。"


class ContinuousPlanningNextActVariables(BaseModel):
    context_block: str = "暂无前文上下文"
    current_act_title: str = "未命名幕"
    current_act_description: str = "无"
    current_act_number: int = Field(ge=0)
    next_act_number: int = Field(ge=1)


PLANNING_QUICK_MACRO_CONTRACT = PromptContract(
    node_key=PLANNING_QUICK_MACRO,
    version="1.0.0",
    variables_schema=PlanningQuickMacroVariables,
    generation_profile="planning_macro",
)

PLANNING_PRECISE_MACRO_CONTRACT = PromptContract(
    node_key=PLANNING_PRECISE_MACRO,
    version="1.0.0",
    variables_schema=PlanningPreciseMacroVariables,
    generation_profile="planning_macro",
)

PLANNING_PRECISE_VOLUME_CONTRACT = PromptContract(
    node_key=PLANNING_PRECISE_VOLUME,
    version="1.0.0",
    variables_schema=PlanningPreciseVolumeVariables,
    generation_profile="planning_macro",
)

PLANNING_PRECISE_REPAIR_CONTRACT = PromptContract(
    node_key=PLANNING_PRECISE_REPAIR,
    version="1.0.0",
    variables_schema=PlanningPreciseRepairVariables,
    generation_profile="planning_repair",
)

PLANNING_ACT_CONTRACT = PromptContract(
    node_key=PLANNING_ACT,
    version="1.0.0",
    variables_schema=PlanningActVariables,
    generation_profile="planning_act",
)

PLANNING_CHAPTER_PREPLAN_CONTRACT = PromptContract(
    node_key=PLANNING_CHAPTER_PREPLAN,
    version="1.0.0",
    variables_schema=PlanningChapterPreplanVariables,
    generation_profile="planning_chapter_preplan",
)

CONTINUOUS_PLANNING_NEXT_ACT_CONTRACT = PromptContract(
    node_key=CONTINUOUS_PLANNING_NEXT_ACT,
    version="1.0.0",
    variables_schema=ContinuousPlanningNextActVariables,
    generation_profile="planning_act",
)
