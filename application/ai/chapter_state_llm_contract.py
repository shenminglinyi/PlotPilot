"""章节状态提取：LLM JSON 契约与 ChapterState 映射。

与 `StateExtractor` 共用：提示词与 Pydantic 根对象 `extra=forbid`，避免模型塞无关顶层字段。
列表元素为 object（dict），内部键保持宽松，与现有 StateUpdater 消费方式一致。

CPMS 改造：system prompt 不再硬编码，通过 PromptRegistry 从数据库读取。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from application.ai.llm_json_extract import parse_llm_json_to_dict
from infrastructure.ai.prompt_keys import CHAPTER_STATE_EXTRACTION
from infrastructure.ai.prompt_utils import get_required_prompt_system
from domain.novel.value_objects.chapter_state import ChapterState

logger = logging.getLogger(__name__)

# 防止异常大响应拖垮下游；正常章节提取远小于此
_MAX_ITEMS = 500

# CPMS: 提示词节点 key（对应 prompts_extraction.json 中的条目）
_CHAPTER_STATE_NODE_KEY = CHAPTER_STATE_EXTRACTION


class ChapterStateLlmPayload(BaseModel):
    """LLM 应返回的根对象：仅允许下列九个数组键。"""

    model_config = ConfigDict(extra="forbid")

    new_characters: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    character_actions: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    relationship_changes: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    foreshadowing_planted: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    foreshadowing_resolved: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    events: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    timeline_events: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    advanced_storylines: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)
    new_storylines: List[Dict[str, Any]] = Field(default_factory=list, max_length=_MAX_ITEMS)


def build_chapter_state_extraction_system_prompt() -> str:
    """Build the chapter-state extraction system prompt from CPMS only."""
    return get_required_prompt_system(_CHAPTER_STATE_NODE_KEY)


def parse_chapter_state_llm_response(
    raw: str,
) -> Tuple[Optional[ChapterStateLlmPayload], List[str]]:
    data, errs = parse_llm_json_to_dict(raw)
    if data is None:
        return None, errs
    try:
        return ChapterStateLlmPayload.model_validate(data), []
    except ValidationError as e:
        err_list = e.errors()
        msg = "; ".join(
            f"{'/'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg', '')}"
            for err in err_list[:12]
        )
        return None, [msg or str(e)]


def chapter_state_payload_to_domain(payload: ChapterStateLlmPayload) -> ChapterState:
    return ChapterState(
        new_characters=[dict(x) for x in payload.new_characters],
        character_actions=[dict(x) for x in payload.character_actions],
        relationship_changes=[dict(x) for x in payload.relationship_changes],
        foreshadowing_planted=[dict(x) for x in payload.foreshadowing_planted],
        foreshadowing_resolved=[dict(x) for x in payload.foreshadowing_resolved],
        events=[dict(x) for x in payload.events],
        timeline_events=[dict(x) for x in payload.timeline_events],
        advanced_storylines=[dict(x) for x in payload.advanced_storylines],
        new_storylines=[dict(x) for x in payload.new_storylines],
    )


def empty_chapter_state() -> ChapterState:
    """契约校验失败时的安全回退（与旧版 _EMPTY_STATE 语义一致）。"""
    return ChapterState(
        new_characters=[],
        character_actions=[],
        relationship_changes=[],
        foreshadowing_planted=[],
        foreshadowing_resolved=[],
        events=[],
        timeline_events=[],
        advanced_storylines=[],
        new_storylines=[],
    )


def chapter_state_openai_function_tool() -> Dict[str, Any]:
    """可选：接入 function calling 时使用。"""
    schema = ChapterStateLlmPayload.model_json_schema(mode="validation")
    return {
        "type": "function",
        "function": {
            "name": "submit_chapter_state_extraction",
            "description": "提交从章节正文提取的结构化状态；根对象仅含六个约定数组键。",
            "parameters": schema,
        },
    }
