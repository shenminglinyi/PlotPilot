"""script-generation 能力契约。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import SCRIPT_GENERATION


class ScriptGenerationVariables(BaseModel):
    """六模块剧本生成输入。"""

    outline: str = Field(min_length=1, description="章节大纲")
    context: str = Field(min_length=1, description="完整上下文（Bible + 前情提要 + 近期章节 + 向量召回）")
    storyline_context: str = Field(default="", description="故事线上下文")
    plot_tension: str = Field(default="", description="情节张力信息")
    style_summary: str = Field(default="", description="风格指纹摘要")
    target_words: str = Field(default="3000-4000", description="章节目标字数")


SCRIPT_GENERATION_CONTRACT = PromptContract(
    node_key=SCRIPT_GENERATION,
    version="1.0.0",
    variables_schema=ScriptGenerationVariables,
    generation_profile="script_generation",
)
