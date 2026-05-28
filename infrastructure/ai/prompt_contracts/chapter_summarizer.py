"""chapter-summarizer 能力契约。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_keys import CHAPTER_SUMMARIZER


class ChapterSummarizerVariables(BaseModel):
    """章节摘要输入。"""

    content: str = Field(min_length=1, description="章节正文")
    max_length: int = Field(default=300, ge=1, le=5000, description="摘要最大字符数")


CHAPTER_SUMMARIZER_CONTRACT = PromptContract(
    node_key=CHAPTER_SUMMARIZER,
    version="1.0.0",
    variables_schema=ChapterSummarizerVariables,
    generation_profile="chapter_summarizer",
    target_models=("claude-3.5-sonnet", "gpt-4.1"),
)
