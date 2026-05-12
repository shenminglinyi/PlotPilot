"""LLM 异步提取器：从正文中抽取持有者变更、损毁、修复等高价值事件。"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是一个叙事分析引擎。根据小说章节正文，识别道具相关事件。"
    "只输出 JSON 数组，不要 markdown 围栏，不要解释。"
)

_SCHEMA = """输出格式（JSON 数组）：
[
  {
    "prop_id": "...",
    "event_type": "TRANSFERRED|DAMAGED|REPAIRED|UPGRADED|RESOLVED",
    "actor_character": "角色名（可选）",
    "from_holder": "转出方角色名（TRANSFERRED 时填）",
    "to_holder": "转入方角色名（TRANSFERRED 时填）",
    "description": "一句话描述"
  }
]
无相关事件时输出空数组 []"""


class LlmExtractor:
    """LLM 提取器 — 仅提取高价值事件（TRANSFERRED/DAMAGED/REPAIRED/RESOLVED）。"""

    priority: int = 10
    name: str = "llm"

    def __init__(self, llm_service):
        self._llm = llm_service

    async def extract(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        active_props: List[dict],
    ) -> List[PropEvent]:
        if not active_props or len(content.strip()) < 300:
            return []

        props_summary = "\n".join(
            f"- {p['name']}（id={p['id']}，持有者={p.get('holder', '无')}）"
            for p in active_props[:20]
        )
        user_msg = (
            f"当前 ACTIVE 道具列表：\n{props_summary}\n\n"
            f"章节正文（节选，前 1500 字）：\n{content[:1500]}\n\n"
            f"{_SCHEMA}"
        )

        try:
            from domain.ai.value_objects.prompt import Prompt
            from domain.ai.services.llm_service import GenerationConfig
            result = await self._llm.generate(
                Prompt(system=_SYSTEM, user=user_msg),
                GenerationConfig(max_tokens=600, temperature=0.1),
            )
            raw = result.content if hasattr(result, "content") else str(result)
            items: List[Dict[str, Any]] = json.loads(raw)
            if not isinstance(items, list):
                return []
        except Exception as e:
            logger.warning("[LlmExtractor] 提取失败: %s", e)
            return []

        events: List[PropEvent] = []
        now = datetime.utcnow().isoformat()
        prop_id_set = {p["id"] for p in active_props}
        for item in items:
            pid = item.get("prop_id", "")
            if pid not in prop_id_set:
                continue
            try:
                etype = PropEventType(item["event_type"])
            except ValueError:
                continue
            events.append(PropEvent(
                id=str(uuid.uuid4()),
                prop_id=pid,
                novel_id=novel_id,
                chapter_number=chapter_number,
                event_type=etype,
                source=PropEventSource.AUTO_LLM,
                description=item.get("description", ""),
                created_at=now,
            ))
        return events
