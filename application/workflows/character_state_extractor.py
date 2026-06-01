"""角色状态确定性抽取器。

用于把 Bible 角色聚合转换为冲突检测可消费的状态字典。该模块只读取
结构化字段与公开描述，不调用 LLM，也不把具体题材元素写死进流程。
"""
from __future__ import annotations

import re
from typing import Any, Dict


def extract_bible_entity_states(bible: Any) -> Dict[str, Dict[str, Any]]:
    """从 Bible 聚合提取实体状态。"""
    entity_states: Dict[str, Dict[str, Any]] = {}
    for character in getattr(bible, "characters", []) or []:
        character_id = str(getattr(character, "id", "") or getattr(getattr(character, "character_id", None), "value", "") or "")
        if not character_id:
            continue
        state = extract_character_state(character)
        if state:
            entity_states[character_id] = state
    return entity_states


def extract_character_state(character: Any) -> Dict[str, Any]:
    """从单个角色提取可校验状态。"""
    state: Dict[str, Any] = {}

    attributes = getattr(character, "attributes", None)
    if isinstance(attributes, dict):
        state.update({str(key): value for key, value in attributes.items() if value not in (None, "", [], {})})

    _put_if_present(state, "mental_state", _non_normal(getattr(character, "mental_state", "")))
    _put_if_present(state, "mental_state_reason", getattr(character, "mental_state_reason", ""))
    _put_if_present(state, "verbal_tic", getattr(character, "verbal_tic", ""))
    _put_if_present(state, "idle_behavior", getattr(character, "idle_behavior", ""))
    _put_if_present(state, "core_belief", getattr(character, "core_belief", ""))

    moral_taboos = [str(item).strip() for item in (getattr(character, "moral_taboos", None) or []) if str(item).strip()]
    if moral_taboos:
        state["moral_taboos"] = moral_taboos

    active_wounds = [item for item in (getattr(character, "active_wounds", None) or []) if item]
    if active_wounds:
        state["active_wounds"] = active_wounds

    voice_profile = getattr(character, "voice_profile", None)
    if isinstance(voice_profile, dict):
        cleaned_voice = {str(key): value for key, value in voice_profile.items() if value not in (None, "", [], {})}
        if cleaned_voice:
            state["voice_profile"] = cleaned_voice

    source_text = "\n".join(
        str(value)
        for value in (
            getattr(character, "description", ""),
            getattr(character, "public_profile", ""),
            getattr(character, "core_belief", ""),
        )
        if value
    )
    ability_tags = extract_ability_tags(source_text)
    if ability_tags:
        state["ability_tags"] = ability_tags
        compatible_magic_type = next((tag for tag in ability_tags if tag.endswith("系")), "")
        if compatible_magic_type:
            state.setdefault("magic_type", compatible_magic_type)

    return state


def extract_ability_tags(text: str) -> list[str]:
    """从公开文本中抽取能力标签。

    规则抽取的是“某某系 / 某某属性 / 某某魔法 / 某某异能 / 某某能力”这类
    语言形态，不枚举具体能力名称。
    """
    raw = text or ""
    tags: list[str] = []
    patterns = [
        r"(?:擅长|掌握|使用|拥有|具备|觉醒|修炼|精通|主修|偏向|属于|是|为)([\u4e00-\u9fffA-Za-z0-9]{1,8})系",
        r"([\u4e00-\u9fffA-Za-z0-9]{1,8})系",
        r"(?:擅长|掌握|使用|拥有|具备|觉醒|修炼|精通|主修|偏向|属于|是|为)([\u4e00-\u9fffA-Za-z0-9]{1,8})(?:属性|魔法)",
        r"([\u4e00-\u9fffA-Za-z0-9]{1,8})(?:属性|魔法)",
        r"(?:擅长|掌握|使用|拥有|具备|觉醒|修炼|精通|主修|偏向|属于|是|为)([\u4e00-\u9fffA-Za-z0-9]{1,12})(?:异能|能力)",
        r"([\u4e00-\u9fffA-Za-z0-9]{1,12})(?:异能|能力)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, raw):
            tag = _normalize_ability_tag(match)
            if tag and tag not in tags:
                tags.append(tag)
    return tags[:8]


def _normalize_ability_tag(value: str) -> str:
    tag = re.sub(r"\s+", "", str(value or ""))
    tag = re.sub(r"^.*(?:擅长|掌握|使用|拥有|具备|觉醒|修炼|精通|主修|偏向|属于|是|为)", "", tag)
    if not tag:
        return ""
    if tag.endswith("系"):
        return tag
    if len(tag) <= 8:
        return f"{tag}系"
    return tag


def _put_if_present(state: Dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        state[key] = value


def _non_normal(value: Any) -> str:
    text = str(value or "").strip()
    return "" if not text or text.upper() == "NORMAL" else text
