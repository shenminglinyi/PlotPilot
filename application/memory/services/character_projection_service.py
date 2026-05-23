from __future__ import annotations

from typing import Any, Dict, List, Optional

from application.memory.services.character_context_compiler import CharacterContextCompiler
from application.memory.services.legacy_memory_importer import LegacyMemoryImporter
from application.memory.services.narrative_memory_service import NarrativeMemoryService
from domain.memory.entities import MemoryProjection


class CharacterProjectionService:
    """Builds the v1 character memory projection from new and legacy sources."""

    def __init__(
        self,
        *,
        memory_service: NarrativeMemoryService,
        bible_repository: Any = None,
        character_state_repository: Any = None,
        triple_repository: Any = None,
        debt_repository: Any = None,
    ) -> None:
        self.memory = memory_service
        self.bible_repo = bible_repository
        self.character_state_repo = character_state_repository
        self.triple_repo = triple_repository
        self.debt_repo = debt_repository
        self.compiler = CharacterContextCompiler()
        self.importer = LegacyMemoryImporter(memory_service)

    def get_projection(self, novel_id: str, character_id: str, *, rebuild: bool = True) -> Dict[str, Any]:
        if rebuild:
            return self.rebuild_projection(novel_id, character_id).data
        existing = self.memory.get_projection(novel_id, character_id)
        if existing:
            return existing.data
        return self.rebuild_projection(novel_id, character_id).data

    def rebuild_projection(self, novel_id: str, character_id: str) -> MemoryProjection:
        char = self._get_bible_character(novel_id, character_id)
        name = getattr(char, "name", "") or character_id
        self.memory.ensure_entity(novel_id, character_id, canonical_name=name)

        state = self.character_state_repo.get(character_id, novel_id) if self.character_state_repo else None
        if state:
            self.importer.import_character_state(novel_id, character_id, state, name=name)

        atoms = self.memory.repo.get_atoms_for_entity(novel_id, character_id, statuses=["confirmed", "candidate"])
        confirmed = [a for a in atoms if a.status == "confirmed"]
        candidates = [a for a in atoms if a.status == "candidate"]

        scars = [a.payload for a in confirmed if a.memory_type == "scar"]
        motivations = [a.payload for a in confirmed if a.memory_type == "motivation"]
        emotions = [a.payload for a in confirmed if a.memory_type == "emotion"]
        states = [a for a in confirmed if a.memory_type == "state"]
        current_summary = ""
        if states:
            current_summary = str(states[0].payload.get("summary") or states[0].payload.get("mental_state") or "")
        elif state:
            current_summary = getattr(state, "current_state_summary", "") or ""
        elif getattr(char, "mental_state", ""):
            current_summary = getattr(char, "mental_state")

        projection: Dict[str, Any] = {
            "novel_id": novel_id,
            "entity_id": character_id,
            "character_id": character_id,
            "name": name,
            "constitution": self._constitution(char),
            "current_state": {
                "summary": current_summary,
                "reason": getattr(char, "mental_state_reason", "") if char else "",
                "last_updated_chapter": getattr(state, "last_updated_chapter", 0) if state else 0,
            },
            "active_scars": scars[:8],
            "active_motivations": motivations[:8],
            "emotional_arc": sorted(emotions, key=lambda x: int(x.get("chapter", 0) or 0))[-12:],
            "relationships": self._relationships(novel_id, character_id, name),
            "knowledge_boundary": {"known": [], "unknown": []},
            "voice_fingerprint": self._voice(char),
            "arc_debts": self._arc_debts(novel_id, character_id, name),
            "recent_evidence": [a.to_dict() for a in atoms[:12]],
            "candidate_memories": [a.to_dict() for a in candidates[:20]],
            "context_locks": {},
        }
        projection["context_locks"] = self.compiler.compile(projection)

        out = MemoryProjection(novel_id=novel_id, entity_id=character_id, data=projection)
        return self.memory.save_projection(out)

    def _get_bible_character(self, novel_id: str, character_id: str) -> Optional[Any]:
        if not self.bible_repo:
            return None
        try:
            from domain.novel.value_objects.novel_id import NovelId

            bible = self.bible_repo.get_by_novel_id(NovelId(novel_id))
            for c in getattr(bible, "characters", []) or []:
                cid = getattr(c, "character_id", None)
                raw = cid.value if hasattr(cid, "value") else getattr(c, "id", "")
                if str(raw) == str(character_id):
                    return c
        except Exception:
            return None
        return None

    @staticmethod
    def _constitution(char: Optional[Any]) -> Dict[str, Any]:
        if not char:
            return {}
        return {
            "public_profile": getattr(char, "public_profile", "") or getattr(char, "description", ""),
            "hidden_profile": getattr(char, "hidden_profile", ""),
            "reveal_chapter": getattr(char, "reveal_chapter", None),
            "core_belief": getattr(char, "core_belief", ""),
            "moral_taboos": list(getattr(char, "moral_taboos", []) or []),
            "active_wounds": list(getattr(char, "active_wounds", []) or []),
        }

    @staticmethod
    def _voice(char: Optional[Any]) -> Dict[str, Any]:
        if not char:
            return {}
        voice = dict(getattr(char, "voice_profile", None) or {})
        if getattr(char, "verbal_tic", ""):
            phrases = list(voice.get("catchphrases") or [])
            if getattr(char, "verbal_tic") not in phrases:
                phrases.append(getattr(char, "verbal_tic"))
            voice["catchphrases"] = phrases
        if getattr(char, "idle_behavior", ""):
            voice["idle_behavior"] = getattr(char, "idle_behavior")
        return voice

    def _relationships(self, novel_id: str, character_id: str, name: str) -> List[Dict[str, Any]]:
        if not self.triple_repo:
            return []
        try:
            triples = self.triple_repo.get_by_entity_ids_sync(novel_id, [character_id, name])
            out = []
            for t in triples[:20]:
                out.append({
                    "subject": getattr(t, "subject_id", ""),
                    "predicate": getattr(t, "predicate", ""),
                    "object": getattr(t, "object_id", ""),
                    "description": getattr(t, "description", ""),
                    "confidence": getattr(t, "confidence", 0.5),
                })
            return out
        except Exception:
            return []

    def _arc_debts(self, novel_id: str, character_id: str, name: str) -> List[Dict[str, Any]]:
        if not self.debt_repo:
            return []
        try:
            debts = self.debt_repo.get_by_entity(novel_id, character_id)
            debts += self.debt_repo.get_by_entity(novel_id, name)
            return [d.to_dict() if hasattr(d, "to_dict") else dict(d) for d in debts[:10]]
        except Exception:
            return []
