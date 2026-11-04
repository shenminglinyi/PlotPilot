from __future__ import annotations

from typing import Any, Dict

from application.memory.services.narrative_memory_service import NarrativeMemoryService


class LegacyMemoryImporter:
    """LEGACY(迁移工具，完成后删除)：将旧版角色状态幂等镜像为 MemoryAtom 行。

    仅限显式迁移调用（如 chapter_narrative_sync 的旧数据导入），非运行路径回退。
    """

    def __init__(self, memory_service: NarrativeMemoryService):
        self.memory = memory_service

    def import_character_state(self, novel_id: str, character_id: str, state: Any, *, name: str = "") -> None:
        self.memory.ensure_entity(novel_id, character_id, canonical_name=name or character_id)
        for scar in getattr(state, "scars", []) or []:
            payload = scar.to_dict() if hasattr(scar, "to_dict") else dict(scar)
            self.memory.remember(
                novel_id,
                character_id,
                "scar",
                payload,
                source="legacy_character_state",
                status="confirmed",
                chapter_number=payload.get("source_chapter") or getattr(state, "last_updated_chapter", None),
                text_span=payload.get("source_event") or payload.get("impact") or "",
                confidence=0.85,
            )
        for motivation in getattr(state, "motivations", []) or []:
            payload = motivation.to_dict() if hasattr(motivation, "to_dict") else dict(motivation)
            self.memory.remember(
                novel_id,
                character_id,
                "motivation",
                payload,
                source="legacy_character_state",
                status="confirmed",
                chapter_number=payload.get("source_chapter") or getattr(state, "last_updated_chapter", None),
                text_span=payload.get("source_event") or payload.get("description") or "",
                confidence=0.85,
            )
        for node in getattr(state, "emotional_arc", []) or []:
            payload = node.to_dict() if hasattr(node, "to_dict") else dict(node)
            self.memory.remember(
                novel_id,
                character_id,
                "emotion",
                payload,
                source="legacy_character_state",
                status="confirmed",
                chapter_number=payload.get("chapter") or getattr(state, "last_updated_chapter", None),
                text_span=payload.get("trigger") or payload.get("emotion") or "",
                confidence=0.8,
            )
        summary = getattr(state, "current_state_summary", "") or ""
        if summary:
            self.memory.remember(
                novel_id,
                character_id,
                "state",
                {"summary": summary, "last_updated_chapter": getattr(state, "last_updated_chapter", 0)},
                source="legacy_character_state",
                status="confirmed",
                chapter_number=getattr(state, "last_updated_chapter", None),
                text_span=summary,
                confidence=0.85,
            )

    def remember_bundle_item(
        self,
        novel_id: str,
        character_id: str,
        memory_type: str,
        payload: Dict[str, Any],
        *,
        chapter_number: int,
        name: str = "",
        source: str = "chapter_extract",
        status: str = "candidate",
        confidence: float = 0.5,
    ) -> None:
        self.memory.ensure_entity(novel_id, character_id, canonical_name=name or character_id)
        text_span = (
            str(payload.get("source_event") or payload.get("content") or payload.get("description")
                or payload.get("mental_state") or payload.get("predicate") or "")[:240]
        )
        self.memory.remember(
            novel_id,
            character_id,
            memory_type,
            payload,
            source=source,
            status=status,
            chapter_number=chapter_number,
            text_span=text_span,
            confidence=confidence,
        )

