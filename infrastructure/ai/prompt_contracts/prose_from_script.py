"""prose-from-script 能力契约。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import PROSE_FROM_SCRIPT


class ProseFromScriptVariables(BaseModel):
    """剧本转正文输入。"""

    script: str = Field(min_length=1, description="六模块导演剧本")
    outline: str = Field(min_length=1, description="章节大纲")
    context: str = Field(default="", description="完整上下文（可选；正文阶段默认不注入，prompt 引用 {context} 时才传入）")
    target_words: str = Field(default="3000-4000", description="章节目标字数")


PROSE_FROM_SCRIPT_CONTRACT = PromptContract(
    node_key=PROSE_FROM_SCRIPT,
    version="1.0.0",
    variables_schema=ProseFromScriptVariables,
    generation_profile="prose_from_script",
)
