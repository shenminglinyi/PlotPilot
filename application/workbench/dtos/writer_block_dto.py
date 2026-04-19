"""Writer Block 数据传输对象"""
from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TensionSlingshotRequest(BaseModel):
    """张力弹弓请求：与 POST JSON body 一致，由 FastAPI / Pydantic 做校验。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    novel_id: str = Field(..., min_length=1, description="小说 ID，须与路径参数一致")
    chapter_number: int = Field(..., ge=1, description="目标章节序号")
    stuck_reason: Optional[str] = Field(
        default=None,
        description="作者自述的卡文原因，可选",
    )

    @field_validator("stuck_reason", mode="before")
    @classmethod
    def empty_stuck_reason_to_none(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            return value.strip()
        return value


@dataclass
class TensionDiagnosis:
    """张力诊断结果 DTO"""
    diagnosis: str
    tension_level: str  # low/medium/high
    missing_elements: List[str]
    suggestions: List[str]
