"""style-analysis 能力契约。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import STYLE_ANALYSIS


class StyleAnalysisVariables(BaseModel):
    """章节文风指纹提取输入。"""

    content: str = Field(min_length=1, description="待分析章节片段")


STYLE_ANALYSIS_CONTRACT = PromptContract(
    node_key=STYLE_ANALYSIS,
    version="1.0.0",
    variables_schema=StyleAnalysisVariables,
    generation_profile="voice_style_analysis",
    target_models=("claude-3.5-sonnet", "gpt-4.1"),
)
