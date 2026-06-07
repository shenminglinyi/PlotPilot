"""voice-baseline-analysis 能力契约。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import VOICE_BASELINE_ANALYSIS


class VoiceBaselineAnalysisVariables(BaseModel):
    """文风基准提取输入。"""

    style_data: str = Field(min_length=1, description="多个章节的文风向量数据")


VOICE_BASELINE_ANALYSIS_CONTRACT = PromptContract(
    node_key=VOICE_BASELINE_ANALYSIS,
    version="1.0.0",
    variables_schema=VoiceBaselineAnalysisVariables,
    generation_profile="voice_baseline_analysis",
    target_models=("claude-3.5-sonnet", "gpt-4.1"),
)
