"""读者模拟 Agent — LLM 输出的 Pydantic 结构化模型。

与 prompt 约定的 JSON 字段一致；额外字段忽略。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReaderDimensionScores(BaseModel):
    """单个读者视角的四维度评分"""

    model_config = ConfigDict(extra="ignore")

    suspense_retention: float = Field(
        default=50.0,
        description="悬疑保持度 (0-100): 本章是否让读者产生「接下来会怎样」的好奇",
    )
    thrill_score: float = Field(
        default=50.0,
        description="爽感评分 (0-100): 本章是否提供了令人满足的情绪高潮或反转",
    )
    churn_risk: float = Field(
        default=30.0,
        description="劝退风险 (0-100): 读者在本章后弃书的概率，越低越好",
    )
    emotional_resonance: float = Field(
        default=50.0,
        description="情感共鸣度 (0-100): 本章是否触动读者情感",
    )

    @field_validator(
        "suspense_retention", "thrill_score", "churn_risk", "emotional_resonance",
        mode="before",
    )
    @classmethod
    def clamp_score(cls, value: object) -> float:
        """将评分归一到 0-100 范围。"""
        if value is None:
            return 50.0
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 50.0
        return max(0.0, min(100.0, v))


class SingleReaderFeedbackPayload(BaseModel):
    """单个读者人设的 LLM 输出"""

    model_config = ConfigDict(extra="ignore")

    persona: str = Field(description="读者人设标识: hardcore / casual / nitpicker")
    scores: ReaderDimensionScores
    one_line_verdict: str = Field(
        default="",
        description="一句话总评（口语化，带该读者的语气特色）",
    )
    highlights: List[str] = Field(
        default_factory=list,
        description="本章亮点（该读者视角）",
    )
    pain_points: List[str] = Field(
        default_factory=list,
        description="本章痛点 / 劝退点",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="改进建议",
    )

    @field_validator("persona", mode="before")
    @classmethod
    def normalize_persona(cls, value: object) -> str:
        if value is None:
            return "casual"
        raw = str(value).strip().lower()
        mapping = {
            "hardcore": "hardcore",
            "硬核粉": "hardcore",
            "硬核": "hardcore",
            "casual": "casual",
            "休闲读者": "casual",
            "休闲": "casual",
            "nitpicker": "nitpicker",
            "挑刺党": "nitpicker",
            "挑刺": "nitpicker",
        }
        return mapping.get(raw, raw)


class ReaderSimulationLlmPayload(BaseModel):
    """完整的 LLM 输出——包含三个读者视角的反馈"""

    model_config = ConfigDict(extra="ignore")

    feedbacks: List[SingleReaderFeedbackPayload] = Field(
        default_factory=list,
        description="三个读者人设的反馈列表",
    )
    overall_readability: float = Field(
        default=50.0,
        description="综合可读性 (0-100)",
    )
    chapter_hook_strength: str = Field(
        default="medium",
        description="章末钩子强度: weak / medium / strong",
    )
    pacing_verdict: str = Field(
        default="",
        description="节奏总评（一句话）",
    )

    @field_validator("overall_readability", mode="before")
    @classmethod
    def clamp_readability(cls, value: object) -> float:
        if value is None:
            return 50.0
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 50.0
        return max(0.0, min(100.0, v))

    @field_validator("chapter_hook_strength", mode="before")
    @classmethod
    def normalize_hook(cls, value: object) -> str:
        if value is None:
            return "medium"
        raw = str(value).strip().lower()
        mapping = {
            "weak": "weak", "弱": "weak", "w": "weak",
            "medium": "medium", "中": "medium", "m": "medium",
            "strong": "strong", "强": "strong", "s": "strong",
        }
        return mapping.get(raw, "medium")
