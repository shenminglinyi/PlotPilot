"""LLM 异步提取器：从正文中抽取持有者变更、损毁、修复等高价值事件。"""
from __future__ import annotations
import json
import logging
import uuid
from typing import Any, Dict, List

from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource
from domain.shared.time_utils import utcnow_iso

logger = logging.getLogger(__name__)


class LlmExtractor:
    """LLM 提取器 — 仅提取高价值事件（TRANSFERRED/DAMAGED/REPAIRED/RESOLVED）。"""

    priority: int = 10
    name: str = "llm"

    def __init__(self, llm_service, entity_resolver=None):
        self._llm = llm_service
        self._entity_resolver = entity_resolver

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

        from infrastructure.ai.prompt_keys import PROP_EVENT_EXTRACTION
        from infrastructure.ai.prompt_utils import render_required_prompt

        variables = {
            "props_summary": props_summary,
            "chapter_excerpt": content[:1500],
        }
        prompt = render_required_prompt(PROP_EVENT_EXTRACTION, variables)

        try:
            from domain.ai.services.llm_service import GenerationConfig
            result = await self._llm.generate(
                prompt,
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
        now = utcnow_iso()
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
                actor_character_id=self._resolve_character_id(
                    novel_id, item.get("actor_character", "")
                ),
                from_holder_id=self._resolve_character_id(
                    novel_id, item.get("from_holder", "")
                ),
                to_holder_id=self._resolve_character_id(
                    novel_id, item.get("to_holder", "")
                ),
                created_at=now,
            ))
        return events

    def _resolve_character_id(self, novel_id: str, raw: str) -> str | None:
        if not raw or not self._entity_resolver:
            return None
        entity = self._entity_resolver.resolve(
            novel_id, raw, allowed_types=["character"]
        )
        if not entity:
            return None
        return entity.id
