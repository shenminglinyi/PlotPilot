"""EmotionLedger LLM 提取器 — 从章节正文提取情绪账本变更"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from application.ai.llm_json_extract import parse_llm_json_to_dict
from domain.ai.services.llm_service import GenerationConfig
from engine.core.value_objects.emotion_ledger import (
    EmotionLedger,
    EmotionalWound,
    EmotionalBoon,
    PowerShift,
    OpenLoop,
)
from infrastructure.ai.prompt_keys import EMOTION_LEDGER_EXTRACTION
from infrastructure.ai.prompt_utils import render_required_prompt

logger = logging.getLogger(__name__)

_MAX_CHAPTER_CHARS = 8000
_MAX_ITEMS_PER_CATEGORY = 3

class EmotionLedgerExtractionError(RuntimeError):
    """情绪账本 LLM 提取失败；禁止用空增量伪装成功。"""


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
        """调用 LLM 提取本章情绪账本变更。"""
        content = (chapter_content or "").strip()
        if len(content) < 100:
            return _empty_deltas()

        if self._llm is None:
            logger.debug("EmotionLedgerExtractor: llm_service 未配置，跳过提取")
            return _empty_deltas()

        prompt = self._build_prompt(content, chapter_number, current_ledger)
        result = await self._llm.generate(
            prompt=prompt,
            config=GenerationConfig(max_tokens=1500, temperature=0.3),
        )
        raw = result.content if hasattr(result, "content") else str(result)
        data, errors = parse_llm_json_to_dict(raw)
        if errors or not data:
            message = "; ".join(errors) if errors else "empty JSON object"
            logger.error("EmotionLedger JSON 解析失败: %s", message)
            raise EmotionLedgerExtractionError(f"情绪账本 LLM 输出无法解析: {message}")
        return _normalize_deltas(data)

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

    def _build_prompt(
        self,
        chapter_content: str,
        chapter_number: int,
        current_ledger: EmotionLedger,
    ):
        truncated = chapter_content[:_MAX_CHAPTER_CHARS]
        if len(chapter_content) > _MAX_CHAPTER_CHARS:
            truncated += "\n...(正文已截断)"

        open_loops = [
            ol.description for ol in current_ledger.open_loops if ol.description
        ]
        open_loops_text = "\n".join(f"- {d}" for d in open_loops) if open_loops else "（无）"

        return render_required_prompt(
            EMOTION_LEDGER_EXTRACTION,
            {
                "chapter_number": chapter_number,
                "open_loops": open_loops_text,
                "chapter_content": truncated,
            },
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
