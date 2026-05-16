from __future__ import annotations
import json
from typing import List, Optional

from domain.shared.time_utils import utcnow_iso

from domain.character.entities.character import Character
from domain.character.repositories.character_repository import CharacterRepository
from domain.character.value_objects.character_id import CharacterId


def _row_to_character(row) -> Character:
    d = dict(row)
    return Character(
        id=CharacterId(d["id"]),
        novel_id=d["novel_id"],
        name=d["name"],
        description=d.get("description", ""),
        public_profile=d.get("public_profile", ""),
        hidden_profile=d.get("hidden_profile", ""),
        reveal_chapter=d.get("reveal_chapter"),
        role=d.get("role", ""),
        faction_id=d.get("faction_id"),
        verbal_tic=d.get("verbal_tic", ""),
        idle_behavior=d.get("idle_behavior", ""),
        voice_style=d.get("voice_style", ""),
        sentence_pattern=d.get("sentence_pattern", ""),
        speech_tempo=d.get("speech_tempo", ""),
        core_belief=d.get("core_belief", ""),
        moral_taboos=json.loads(d.get("moral_taboos_json") or "[]"),
        active_wounds=json.loads(d.get("active_wounds_json") or "[]"),
        mental_state=d.get("mental_state", "NORMAL"),
        mental_state_reason=d.get("mental_state_reason", ""),
        emotional_arc=json.loads(d.get("emotional_arc_json") or "[]"),
        current_state_summary=d.get("current_state_summary", ""),
        last_updated_chapter=d.get("last_updated_chapter", 0),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


class SqliteUnifiedCharacterRepository(CharacterRepository):
    def __init__(self, db):
        self._db = db

    def get(self, character_id: CharacterId) -> Optional[Character]:
        row = self._db.fetch_one(
            "SELECT * FROM unified_characters WHERE id = ?", (character_id.value,)
        )
        return _row_to_character(row) if row else None

    def list_by_novel(self, novel_id: str) -> List[Character]:
        rows = self._db.fetch_all(
            "SELECT * FROM unified_characters WHERE novel_id = ? ORDER BY name",
            (novel_id,),
        )
        return [_row_to_character(r) for r in rows]

    def save(self, character: Character) -> None:
        now = utcnow_iso()
        self._db.execute(
            """INSERT INTO unified_characters (
                id, novel_id, name, description, public_profile, hidden_profile,
                reveal_chapter, role, faction_id,
                verbal_tic, idle_behavior, voice_style, sentence_pattern, speech_tempo,
                core_belief, moral_taboos_json, active_wounds_json,
                mental_state, mental_state_reason,
                emotional_arc_json, current_state_summary, last_updated_chapter,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                public_profile=excluded.public_profile, hidden_profile=excluded.hidden_profile,
                reveal_chapter=excluded.reveal_chapter, role=excluded.role,
                faction_id=excluded.faction_id,
                verbal_tic=excluded.verbal_tic, idle_behavior=excluded.idle_behavior,
                voice_style=excluded.voice_style, sentence_pattern=excluded.sentence_pattern,
                speech_tempo=excluded.speech_tempo, core_belief=excluded.core_belief,
                moral_taboos_json=excluded.moral_taboos_json,
                active_wounds_json=excluded.active_wounds_json,
                mental_state=excluded.mental_state,
                mental_state_reason=excluded.mental_state_reason,
                emotional_arc_json=excluded.emotional_arc_json,
                current_state_summary=excluded.current_state_summary,
                last_updated_chapter=excluded.last_updated_chapter,
                updated_at=excluded.updated_at""",
            (
                character.id.value, character.novel_id, character.name,
                character.description, character.public_profile, character.hidden_profile,
                character.reveal_chapter, character.role, character.faction_id,
                character.verbal_tic, character.idle_behavior, character.voice_style,
                character.sentence_pattern, character.speech_tempo, character.core_belief,
                json.dumps(character.moral_taboos, ensure_ascii=False),
                json.dumps(character.active_wounds, ensure_ascii=False),
                character.mental_state, character.mental_state_reason,
                json.dumps(character.emotional_arc, ensure_ascii=False),
                character.current_state_summary, character.last_updated_chapter,
                character.created_at, now,
            ),
        )
        self._db.get_connection().commit()

    def delete(self, character_id: CharacterId) -> None:
        self._db.execute(
            "DELETE FROM unified_characters WHERE id = ?", (character_id.value,)
        )
        self._db.get_connection().commit()
