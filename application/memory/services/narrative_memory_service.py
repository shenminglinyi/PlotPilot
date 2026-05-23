from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain.memory.entities import MemoryAtom, MemoryProjection, NarrativeEntity


class NarrativeMemoryService:
    """Small application facade over MemoryAtom persistence."""

    def __init__(self, repository: Any):
        self.repo = repository

    def ensure_entity(
        self,
        novel_id: str,
        entity_id: str,
        *,
        entity_type: str = "character",
        canonical_name: str = "",
        aliases: Optional[List[str]] = None,
    ) -> NarrativeEntity:
        return self.repo.upsert_entity(
            NarrativeEntity(
                id=entity_id,
                novel_id=novel_id,
                entity_type=entity_type,
                canonical_name=canonical_name,
                aliases=aliases or [],
            )
        )

    def remember(
        self,
        novel_id: str,
        entity_id: str,
        memory_type: str,
        payload: Dict[str, Any],
        *,
        entity_type: str = "character",
        scope: str = "global",
        source: str = "manual",
        status: str = "candidate",
        chapter_number: Optional[int] = None,
        text_span: str = "",
        confidence: float = 0.5,
    ) -> MemoryAtom:
        return self.repo.upsert_atom(
            MemoryAtom(
                novel_id=novel_id,
                entity_id=entity_id,
                entity_type=entity_type,
                memory_type=memory_type,
                scope=scope,
                source=source,
                status=status,
                payload=payload,
                chapter_number=chapter_number,
                text_span=text_span,
                confidence=confidence,
            )
        )

    def atoms_for_entity(self, novel_id: str, entity_id: str) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self.repo.get_atoms_for_entity(novel_id, entity_id)]

    def candidates_for_chapter(self, novel_id: str, chapter_number: int) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self.repo.get_candidates_for_chapter(novel_id, chapter_number)]

    def update_status(
        self,
        novel_id: str,
        atom_id: str,
        status: str,
        *,
        action: str,
        note: str = "",
    ) -> Optional[MemoryAtom]:
        return self.repo.update_atom_status(novel_id, atom_id, status, action=action, note=note)

    def save_projection(self, projection: MemoryProjection) -> MemoryProjection:
        return self.repo.save_projection(projection)

    def get_projection(
        self,
        novel_id: str,
        entity_id: str,
        projection_type: str = "character",
    ) -> Optional[MemoryProjection]:
        return self.repo.get_projection(novel_id, entity_id, projection_type)
