"""memory-extraction 能力契约。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import MEMORY_EXTRACTION


class MemoryExtractionVariables(BaseModel):
    """章节记忆增量提取输入。"""

    chapter_content: str = Field(min_length=1, description="待分析章节正文")
    chapter_number: int = Field(ge=1, description="章节编号")
    outline: str = Field(default="", description="章节大纲")
    fact_lock_text: str = Field(default="", description="当前事实锁")
    existing_beats_summary: str = Field(default="", description="已完成节拍摘要")
    existing_clues_summary: str = Field(default="", description="已揭露线索摘要")


MEMORY_EXTRACTION_CONTRACT = PromptContract(
    node_key=MEMORY_EXTRACTION,
    version="1.0.0",
    variables_schema=MemoryExtractionVariables,
    generation_profile="memory_extraction",
    target_models=("claude-3.5-sonnet", "gpt-4.1"),
)
