"""LLM 异步提取器：从正文中抽取持有者变更、损毁、修复等高价值事件。"""
from __future__ import annotations
import json
import logging
import uuid
from typing import Any, Dict, List

from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource
from domain.shared.time_utils import utcnow_iso

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a narrative analysis engine. Identify prop-related events from novel chapter text."
    " Only output valid JSON array, no markdown fences, no explanation."
)

_SCHEMA = """Output format (JSON array):
[
  {
    "prop_id": "...",
    "event_type": "TRANSFERRED|DAMAGED|REPAIRED|UPGRADED|RESOLVED",
    "actor_character": "character name (optional)",
    "from_holder": "transfer source character (for TRANSFERRED)",
    "to_holder": "transfer target character (for TRANSFERRED)",
    "description": "one-line description"
  }
]
Output empty array [] if no relevant events."""



class LlmExtractor:
    """LLM extractor for high-value prop events (TRANSFERRED/DAMAGED/REPAIRED/RESOLVED)."""

    priority: int = 10
    name: str = "llm"

    def __init__(self, llm_service):
        self._llm = llm_service

    @staticmethod
    def _get_system_prompt() -> str:
        """Get system prompt via CPMS."""
        from infrastructure.ai.prompt_utils import get_prompt_system
        from infrastructure.ai.prompt_keys import PROP_EVENT_EXTRACTION
        return get_prompt_system(PROP_EVENT_EXTRACTION, fallback=_SYSTEM)

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
            f"- {p['name']} (id={p['id']}, holder={p.get('holder', 'none')})"
            for p in active_props[:20]
        )

        # CPMS render
        from infrastructure.ai.prompt_keys import PROP_EVENT_EXTRACTION
        from infrastructure.ai.prompt_registry import get_prompt_registry

        registry = get_prompt_registry()
        variables = {
            "props_summary": props_summary,
            "chapter_excerpt": content[:1500],
            "output_schema": _SCHEMA,
        }
        prompt = registry.render_to_prompt(PROP_EVENT_EXTRACTION, variables)

        # Fallback
        if not prompt:
            from domain.ai.value_objects.prompt import Prompt
            user_msg = (
                f"Current ACTIVE prop list:\n{props_summary}\n\n"
                f"Chapter text (excerpt, first 1500 chars):\n{content[:1500]}\n\n"
                f"{_SCHEMA}"
            )
            prompt = Prompt(system=self._get_system_prompt(), user=user_msg)

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
            logger.warning("[LlmExtractor] extraction failed: %s", e)
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
                created_at=now,
            ))
        return events
