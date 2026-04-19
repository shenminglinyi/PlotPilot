"""张力诊断 LLM 输出的 Pydantic 模型。"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TensionDiagnosisLlmPayload(BaseModel):
    """与 prompt 约定的 JSON 字段一致；额外字段忽略。"""

    model_config = ConfigDict(extra="ignore")

    diagnosis: str
    tension_level: str
    missing_elements: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)

    @field_validator("tension_level", mode="before")
    @classmethod
    def normalize_tension_level(cls, value: object) -> str:
        """将常见别名与中文档位归一为 low / medium / high。"""
        if value is None:
            return "low"

        raw = str(value).strip()
        lower = raw.lower()

        direct = {
            "low": "low",
            "l": "low",
            "1": "low",
            "medium": "medium",
            "mid": "medium",
            "m": "medium",
            "2": "medium",
            "high": "high",
            "h": "high",
            "peak": "high",
            "3": "high",
            "4": "high",
        }
        if lower in direct:
            return direct[lower]

        if "低" in raw:
            return "low"
        if "中" in raw:
            return "medium"
        if "高" in raw or "峰值" in raw:
            return "high"

        return "medium"

    @field_validator("diagnosis", mode="before")
    @classmethod
    def strip_diagnosis(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()
