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
from domain.novel.value_objects.chapter_state import ChapterState

logger = logging.getLogger(__name__)

# 防止异常大响应拖垮下游；正常章节提取远小于此
_MAX_ITEMS = 500

# CPMS: 提示词节点 key（对应 prompts_extraction.json 中的条目）
_CHAPTER_STATE_NODE_KEY = "chapter-state-extraction"

# 硬编码回退（仅在 PromptRegistry 不可用时使用）
_FALLBACK_SYSTEM = """你是一个专业的小说内容分析助手。你的任务是从章节内容中提取结构化信息。

请提取以下信息并以 JSON 格式返回（根对象**仅允许**下列九个键，不要增加其他顶层字段）：

【微观提取（单章精确）】
1. new_characters: 新出现的角色列表，每项为对象，包含 name、description、first_appearance（章节号）
2. character_actions: 角色行为列表，每项包含 character_id、action、chapter
3. relationship_changes: 关系变化列表，每项包含 char1、char2、old_type、new_type、chapter
4. foreshadowing_planted: 埋下的伏笔列表，每项包含 description、chapter
5. foreshadowing_resolved: 解决的伏笔列表，每项包含 foreshadowing_id、chapter
6. events: 事件列表，每项包含 type、description、involved_characters（数组）、chapter

【时间线提取（第一梯队）】
7. timeline_events: 本章发生的关键事件及时间戳，每项包含：
   - event: 事件描述（简短）
   - timestamp: 时间戳（如"第三年春"、"2024-03-15"、"午夜"）
   - timestamp_type: 时间类型（"absolute"=绝对时间、"relative"=相对时间、"vague"=模糊时间）
   注意：只提取文中明确或隐含的时间信息，不要臆造

【故事线提取（第二梯队）】
8. advanced_storylines: 本章推进的已有故事线，每项包含：
   - storyline_id: 故事线ID（如果能识别）或 storyline_name（故事线名称）
   - progress_summary: 本章在该线上的进展（1-2句话）

9. new_storylines: 本章引入的新故事线，每项包含：
   - name: 故事线名称（如"复仇主线"、"师徒暗线"）
   - type: 类型（"main"=主线、"sub"=支线、"hidden"=暗线）
   - description: 故事线描述（1-2句话）
   注意：只在真正开启新线索时提取，不要过度解读

只返回一个 JSON 对象，不要 markdown 代码块、不要前后解释文字。"""


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
    """构建章节状态提取的 system prompt。

    CPMS: 优先从 PromptRegistry 获取（广场可编辑），
    如果 Registry 不可用则回退到硬编码默认值。
    """
    try:
        from infrastructure.ai.prompt_registry import get_prompt_registry
        registry = get_prompt_registry()
        system = registry.get_system(_CHAPTER_STATE_NODE_KEY)
        if system:
            return system
    except Exception as exc:
        logger.debug("PromptRegistry 不可用，使用回退提示词: %s", exc)

    return _FALLBACK_SYSTEM


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
