"""Canonical entity resolver for narrative facts.

The resolver is intentionally application-level: it normalizes entities already
owned by bounded contexts (character, prop, location later) while keeping their
aggregate logic in those contexts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol


@dataclass(frozen=True)
class ResolvedEntity:
    id: str
    entity_type: str
    name: str
    confidence: float
    matched_by: str


class _ListByNovelRepository(Protocol):
    def list_by_novel(self, novel_id: str) -> list: ...


def _norm(value: str) -> str:
    return (value or "").strip().casefold()


class EntityResolver:
    """Resolve names, aliases, and ids into canonical narrative entities."""

    def __init__(
        self,
        *,
        character_repo: Optional[_ListByNovelRepository] = None,
        prop_repo: Optional[_ListByNovelRepository] = None,
    ) -> None:
        self.character_repo = character_repo
        self.prop_repo = prop_repo

    def resolve(
        self,
        novel_id: str,
        raw: str,
        *,
        allowed_types: Optional[Iterable[str]] = None,
    ) -> Optional[ResolvedEntity]:
        query = _norm(raw)
        if not query:
            return None

        allowed = set(allowed_types or ["character", "prop"])
        candidates: list[ResolvedEntity] = []
        if "character" in allowed and self.character_repo:
            candidates.extend(self._character_candidates(novel_id, query))
        if "prop" in allowed and self.prop_repo:
            candidates.extend(self._prop_candidates(novel_id, query))

        if not candidates:
            return None
        return max(candidates, key=lambda c: c.confidence)

    def _character_candidates(self, novel_id: str, query: str) -> list[ResolvedEntity]:
        out: list[ResolvedEntity] = []
        for char in self.character_repo.list_by_novel(novel_id):
            char_id = getattr(getattr(char, "id", None), "value", "")
            name = getattr(char, "name", "") or ""
            if query == _norm(char_id):
                out.append(ResolvedEntity(char_id, "character", name, 1.0, "id"))
            elif query == _norm(name):
                out.append(ResolvedEntity(char_id, "character", name, 0.95, "name"))
        return out

    def _prop_candidates(self, novel_id: str, query: str) -> list[ResolvedEntity]:
        out: list[ResolvedEntity] = []
        for prop in self.prop_repo.list_by_novel(novel_id):
            prop_id = getattr(getattr(prop, "id", None), "value", "")
            name = getattr(prop, "name", "") or ""
            aliases = list(getattr(prop, "aliases", []) or [])
            if query == _norm(prop_id):
                out.append(ResolvedEntity(prop_id, "prop", name, 1.0, "id"))
            elif query == _norm(name):
                out.append(ResolvedEntity(prop_id, "prop", name, 0.95, "name"))
            elif query in {_norm(alias) for alias in aliases}:
                out.append(ResolvedEntity(prop_id, "prop", name, 0.85, "alias"))
        return out
