"""tension-analysis-diagnosis 能力契约。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from application.analyst.tension.schema import TensionDiagnosisLlmPayload
from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import TENSION_ANALYSIS_DIAGNOSIS


class TensionAnalysisDiagnosisVariables(BaseModel):
    """卡文诊断输入。"""

    novel_id: str = Field(min_length=1, description="小说 ID")
    chapter_number: int = Field(ge=1, description="卡文章节号")
    stuck_reason_text: str = Field(default="未提供", description="作者自述的卡文原因")
    events_text: str = Field(default="暂无事件数据", description="近期事件流")
    repository_context: str = Field(default="", description="章节正文、剧情弧等仓储补充上下文")
    stats_text: str = Field(default="", description="统计数据")


TENSION_ANALYSIS_DIAGNOSIS_CONTRACT = PromptContract(
    node_key=TENSION_ANALYSIS_DIAGNOSIS,
    version="1.0.0",
    variables_schema=TensionAnalysisDiagnosisVariables,
    output_schema=TensionDiagnosisLlmPayload,
    generation_profile="tension_diagnosis",
    target_models=("claude-3.5-sonnet", "gpt-4.1"),
)
