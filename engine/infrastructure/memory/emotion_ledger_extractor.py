"""EmotionLedger LLM 提取器 — 从章节正文提取情绪账本变更"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from application.ai.llm_json_extract import parse_llm_json_to_dict
from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from engine.core.value_objects.emotion_ledger import (
    EmotionLedger,
    EmotionalWound,
    EmotionalBoon,
    PowerShift,
    OpenLoop,
)

logger = logging.getLogger(__name__)

_MAX_CHAPTER_CHARS = 8000
_MAX_ITEMS_PER_CATEGORY = 3

_SYSTEM_PROMPT = """你是专业小说编辑。从章节正文中提取情绪账本变更，以小说家视角记录角色心理变化，而非事件流水账。

输出严格 JSON，格式如下：
{
  "wounds": [{"description": "核心损失", "impact": "对心态的影响"}],
  "boons": [{"description": "核心获得", "value": "带来的价值"}],
  "power_shifts": [{"from_state": "之前状态", "to_state": "之后状态", "trigger": "触发原因"}],
  "open_loops": [{"description": "悬念描述", "hint": "暗示线索", "urgency": 0.5}],
  "resolved_loops": ["本章已回收的悬念描述"]
}

规则：
- 只提取本章正文明确发生的情感/局势变化，不要臆造
- 每类最多 3 条；无变化则返回空数组
- resolved_loops 仅填写本章明确回收的已有悬念
- urgency 取值 0.0~1.0
- 只输出 JSON，不要其他文字"""


class EmotionLedgerExtractor:
    """从章节内容提取 EmotionLedger 增量变更"""

    def __init__(self, llm_service=None):
        self._llm = llm_service

    async def extract_deltas(
        self,
        chapter_content: str,
        chapter_number: int,
        current_ledger: EmotionLedger,
    ) -> Dict[str, Any]:
        """调用 LLM 提取本章情绪账本变更。失败时返回空增量。"""
        content = (chapter_content or "").strip()
        if len(content) < 100:
            return _empty_deltas()

        if self._llm is None:
            logger.debug("EmotionLedgerExtractor: llm_service 未配置，跳过提取")
            return _empty_deltas()

        user_prompt = self._build_user_prompt(content, chapter_number, current_ledger)
        try:
            result = await self._llm.generate(
                prompt=Prompt(system=_SYSTEM_PROMPT, user=user_prompt),
                config=GenerationConfig(max_tokens=1500, temperature=0.3),
            )
            raw = result.content if hasattr(result, "content") else str(result)
            data, errors = parse_llm_json_to_dict(raw)
            if errors or not data:
                logger.warning("EmotionLedger JSON 解析失败: %s", errors)
                return _empty_deltas()
            return _normalize_deltas(data)
        except Exception as e:
            logger.warning("EmotionLedger LLM 提取失败: %s", e)
            return _empty_deltas()

    def merge_ledger(
        self,
        current: EmotionLedger,
        deltas: Dict[str, Any],
        chapter_number: int,
    ) -> EmotionLedger:
        """将增量变更合并到现有账本（不可变追加）"""
        ledger = current

        for item in deltas.get("wounds", [])[:_MAX_ITEMS_PER_CATEGORY]:
            wound = EmotionalWound(
                description=str(item.get("description", "")).strip(),
                impact=str(item.get("impact", "")).strip(),
                chapter_number=chapter_number,
            )
            if wound.description:
                ledger = ledger.add_wound(wound)

        for item in deltas.get("boons", [])[:_MAX_ITEMS_PER_CATEGORY]:
            boon = EmotionalBoon(
                description=str(item.get("description", "")).strip(),
                value=str(item.get("value", "")).strip(),
                chapter_number=chapter_number,
            )
            if boon.description:
                ledger = ledger.add_boon(boon)

        for item in deltas.get("power_shifts", [])[:_MAX_ITEMS_PER_CATEGORY]:
            shift = PowerShift(
                from_state=str(item.get("from_state", "")).strip(),
                to_state=str(item.get("to_state", "")).strip(),
                trigger=str(item.get("trigger", "")).strip(),
            )
            if shift.from_state and shift.to_state:
                ledger = ledger.add_power_shift(shift)

        for item in deltas.get("open_loops", [])[:_MAX_ITEMS_PER_CATEGORY]:
            urgency = item.get("urgency", 0.5)
            try:
                urgency = max(0.0, min(1.0, float(urgency)))
            except (TypeError, ValueError):
                urgency = 0.5
            loop = OpenLoop(
                description=str(item.get("description", "")).strip(),
                hint=str(item.get("hint", "")).strip(),
                planted_chapter=chapter_number,
                urgency=urgency,
            )
            if loop.description:
                ledger = ledger.add_open_loop(loop)

        for desc in deltas.get("resolved_loops", []):
            desc = str(desc).strip()
            if desc:
                ledger = ledger.close_loop(desc)

        return ledger

    def _build_user_prompt(
        self,
        chapter_content: str,
        chapter_number: int,
        current_ledger: EmotionLedger,
    ) -> str:
        truncated = chapter_content[:_MAX_CHAPTER_CHARS]
        if len(chapter_content) > _MAX_CHAPTER_CHARS:
            truncated += "\n...(正文已截断)"

        open_loops = [
            ol.description for ol in current_ledger.open_loops if ol.description
        ]
        open_loops_text = "\n".join(f"- {d}" for d in open_loops) if open_loops else "（无）"

        return (
            f"章节号：第{chapter_number}章\n\n"
            f"当前未解悬念：\n{open_loops_text}\n\n"
            f"章节正文：\n{truncated}"
        )


def _empty_deltas() -> Dict[str, Any]:
    return {
        "wounds": [],
        "boons": [],
        "power_shifts": [],
        "open_loops": [],
        "resolved_loops": [],
    }


def _normalize_deltas(data: Dict[str, Any]) -> Dict[str, Any]:
    """规范化 LLM 输出字段名"""
    result = _empty_deltas()

    for key in ("wounds", "boons", "open_loops", "resolved_loops"):
        items = data.get(key, [])
        if isinstance(items, list):
            result[key] = items[:_MAX_ITEMS_PER_CATEGORY]

    shifts = data.get("power_shifts", data.get("powerShifts", []))
    if isinstance(shifts, list):
        normalized_shifts = []
        for item in shifts[:_MAX_ITEMS_PER_CATEGORY]:
            if not isinstance(item, dict):
                continue
            normalized_shifts.append({
                "from_state": item.get("from_state") or item.get("from") or "",
                "to_state": item.get("to_state") or item.get("to") or "",
                "trigger": item.get("trigger", ""),
            })
        result["power_shifts"] = normalized_shifts

    return result
