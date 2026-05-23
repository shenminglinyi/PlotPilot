"""SQLite Bible repository.

Bible-owned world/location/style/timeline data stays in Bible tables; characters
are read and written through unified_characters, the canonical character store.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.bible.entities.bible import Bible
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.mappers.bible_mapper import BibleMapper

logger = logging.getLogger(__name__)


class SqliteBibleRepository(BibleRepository):
    """Persist Bible aggregate data with unified characters as the character truth."""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def _conn(self):
        return self.db.get_connection()

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat()

    def _clear_children(self, conn, novel_id: str) -> None:
        conn.execute("DELETE FROM bible_style_notes WHERE novel_id = ?", (novel_id,))
        conn.execute("DELETE FROM bible_timeline_notes WHERE novel_id = ?", (novel_id,))
        conn.execute("DELETE FROM bible_locations WHERE novel_id = ?", (novel_id,))
        conn.execute("DELETE FROM bible_world_settings WHERE novel_id = ?", (novel_id,))
        conn.execute("DELETE FROM unified_characters WHERE novel_id = ?", (novel_id,))

    def save(self, bible: Bible) -> None:
        novel_id = bible.novel_id.value
        now = self._now()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO bibles (id, novel_id, schema_version, extensions, created_at, updated_at)
                VALUES (?, ?, 1, '{}', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    novel_id = excluded.novel_id,
                    updated_at = excluded.updated_at
                """,
                (bible.id, novel_id, now, now),
            )
            self._clear_children(conn, novel_id)

            for char in bible.characters:
                self._save_unified_character(conn, novel_id, char, now)

            for ws in bible.world_settings:
                conn.execute(
                    """
                    INSERT INTO bible_world_settings
                    (id, novel_id, name, description, setting_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ws.id, novel_id, ws.name, ws.description or "", ws.setting_type or "other", now, now),
                )

            for loc in bible.locations:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO bible_locations
                    (id, novel_id, name, description, location_type, parent_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        loc.id,
                        novel_id,
                        loc.name,
                        loc.description or "",
                        loc.location_type or "other",
                        loc.parent_id,
                        now,
                        now,
                    ),
                )

            for order, note in enumerate(bible.timeline_notes):
                conn.execute(
                    """
                    INSERT INTO bible_timeline_notes
                    (id, novel_id, event, time_point, description, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        note.id,
                        novel_id,
                        note.event or "",
                        note.time_point or "",
                        note.description or "",
                        order,
                        now,
                        now,
                    ),
                )

            for sn in bible.style_notes:
                conn.execute(
                    """
                    INSERT INTO bible_style_notes
                    (id, novel_id, category, content, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (sn.id, novel_id, sn.category, sn.content or "", now, now),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _save_unified_character(self, conn, novel_id: str, char: Any, now: str) -> None:
        cid = char.character_id.value
        voice_profile = getattr(char, "voice_profile", None) or {}
        conn.execute(
            """
            INSERT OR REPLACE INTO unified_characters (
                id, novel_id, name, description, public_profile, hidden_profile,
                reveal_chapter, verbal_tic, idle_behavior, voice_style,
                sentence_pattern, speech_tempo, core_belief, moral_taboos_json,
                active_wounds_json, mental_state, mental_state_reason,
                emotional_arc_json, current_state_summary, last_updated_chapter,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                novel_id,
                char.name,
                char.description or "",
                getattr(char, "public_profile", "") or "",
                getattr(char, "hidden_profile", "") or "",
                getattr(char, "reveal_chapter", None),
                getattr(char, "verbal_tic", "") or "",
                getattr(char, "idle_behavior", "") or "",
                voice_profile.get("style", "") or voice_profile.get("voice_style", "") or "",
                voice_profile.get("sentence_pattern", "") or "",
                voice_profile.get("speech_tempo", "") or "",
                getattr(char, "core_belief", "") or "",
                json.dumps(getattr(char, "moral_taboos", None) or [], ensure_ascii=False),
                json.dumps(getattr(char, "active_wounds", None) or [], ensure_ascii=False),
                getattr(char, "mental_state", None) or "NORMAL",
                getattr(char, "mental_state_reason", None) or "",
                "[]",
                "",
                0,
                now,
                now,
            ),
        )

        for i, rel in enumerate(char.relationships or []):
            rid = f"{cid}-rel-{i}-{uuid.uuid4().hex[:6]}"
            if isinstance(rel, str):
                target_name = rel
                relation = ""
                description = ""
            else:
                if hasattr(rel, "model_dump"):
                    rel_dict = rel.model_dump()
                elif hasattr(rel, "dict"):
                    rel_dict = rel.dict()
                else:
                    rel_dict = rel
                target_name = rel_dict.get("target", "") or ""
                relation = rel_dict.get("relation", "") or ""
                description = rel_dict.get("description", "") or ""
            conn.execute(
                """
                INSERT INTO unified_character_relationships
                (id, character_id, target_name, relation, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (rid, cid, target_name, relation, description),
            )

    def _character_rows(self, novel_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM unified_characters WHERE novel_id = ? ORDER BY id",
            (novel_id,),
        )
        return [dict(r) for r in rows]

    def _rels_for_character(self, character_id: str) -> List[Dict[str, str]]:
        rows = self.db.fetch_all(
            """
            SELECT target_name, relation, description
            FROM unified_character_relationships
            WHERE character_id = ?
            ORDER BY id
            """,
            (character_id,),
        )
        return [
            {
                "target": r["target_name"],
                "relation": r["relation"],
                "description": r["description"],
            }
            for r in rows
        ]

    def _to_mapper_dict(self, bible_id: str, novel_id: str) -> Dict[str, Any]:
        chars_out: List[Dict[str, Any]] = []
        for row in self._character_rows(novel_id):
            chars_out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"] or "",
                    "relationships": self._rels_for_character(row["id"]),
                    "mental_state": row.get("mental_state") or "NORMAL",
                    "mental_state_reason": row.get("mental_state_reason") or "",
                    "verbal_tic": row.get("verbal_tic") or "",
                    "idle_behavior": row.get("idle_behavior") or "",
                    "public_profile": row.get("public_profile") or "",
                    "hidden_profile": row.get("hidden_profile") or "",
                    "reveal_chapter": row.get("reveal_chapter"),
                    "core_belief": row.get("core_belief") or "",
                    "moral_taboos": self._loads(row.get("moral_taboos_json"), []),
                    "voice_profile": {
                        k: v
                        for k, v in {
                            "style": row.get("voice_style") or "",
                            "sentence_pattern": row.get("sentence_pattern") or "",
                            "speech_tempo": row.get("speech_tempo") or "",
                        }.items()
                        if v
                    },
                    "active_wounds": self._loads(row.get("active_wounds_json"), []),
                }
            )

        return {
            "id": bible_id,
            "novel_id": novel_id,
            "characters": chars_out,
            "world_settings": self._world_settings(novel_id),
            "locations": self._locations(novel_id),
            "timeline_notes": self._timeline_notes(novel_id),
            "style_notes": self._style_notes(novel_id),
        }

    @staticmethod
    def _loads(raw: str | None, default):
        if not raw:
            return default
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        return parsed if isinstance(parsed, type(default)) else default

    def _world_settings(self, novel_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM bible_world_settings WHERE novel_id = ? ORDER BY id",
            (novel_id,),
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"] or "",
                "setting_type": r["setting_type"] or "other",
            }
            for r in rows
        ]

    def _locations(self, novel_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM bible_locations WHERE novel_id = ? ORDER BY id",
            (novel_id,),
        )
        locations: List[Dict[str, Any]] = []
        for row in rows:
            r = dict(row)
            item = {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"] or "",
                "location_type": r["location_type"] or "other",
            }
            if r.get("parent_id"):
                item["parent_id"] = r["parent_id"]
            locations.append(item)
        return locations

    def _timeline_notes(self, novel_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            """
            SELECT id, event, time_point, description
            FROM bible_timeline_notes
            WHERE novel_id = ?
            ORDER BY sort_order, id
            """,
            (novel_id,),
        )
        return [
            {
                "id": r["id"],
                "event": r["event"] or "",
                "time_point": r["time_point"] or "",
                "description": r["description"] or "",
            }
            for r in rows
        ]

    def _style_notes(self, novel_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT id, category, content FROM bible_style_notes WHERE novel_id = ? ORDER BY id",
            (novel_id,),
        )
        return [{"id": r["id"], "category": r["category"], "content": r["content"] or ""} for r in rows]

    def get_by_id(self, bible_id: str) -> Optional[Bible]:
        row = self.db.fetch_one("SELECT * FROM bibles WHERE id = ?", (bible_id,))
        if not row:
            return None
        return self._from_row(row)

    def get_by_novel_id(self, novel_id: NovelId) -> Optional[Bible]:
        row = self.db.fetch_one("SELECT * FROM bibles WHERE novel_id = ?", (novel_id.value,))
        if not row:
            return None
        return self._from_row(row)

    def _from_row(self, row) -> Optional[Bible]:
        data = self._to_mapper_dict(row["id"], row["novel_id"])
        try:
            return BibleMapper.from_dict(data)
        except ValueError as e:
            logger.warning("Bible %s invalid: %s", row["id"], e)
            return None

    def delete(self, bible_id: str) -> None:
        row = self.db.fetch_one("SELECT novel_id FROM bibles WHERE id = ?", (bible_id,))
        if not row:
            return
        conn = self._conn()
        try:
            self._clear_children(conn, row["novel_id"])
            conn.execute("DELETE FROM bibles WHERE id = ?", (bible_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def exists(self, bible_id: str) -> bool:
        return self.db.fetch_one("SELECT 1 AS o FROM bibles WHERE id = ?", (bible_id,)) is not None

    def update_character_anchors(
        self,
        novel_id: str,
        character_id: str,
        *,
        mental_state: str,
        verbal_tic: str,
        idle_behavior: str,
    ) -> None:
        row = self.db.fetch_one(
            "SELECT id FROM unified_characters WHERE novel_id = ? AND id = ?",
            (novel_id, character_id),
        )
        if not row:
            from domain.shared.exceptions import EntityNotFoundError

            raise EntityNotFoundError("Character", f"{novel_id}/{character_id}")
        self.db.execute(
            """
            UPDATE unified_characters
            SET mental_state = ?, verbal_tic = ?, idle_behavior = ?, updated_at = ?
            WHERE novel_id = ? AND id = ?
            """,
            (mental_state, verbal_tic, idle_behavior, self._now(), novel_id, character_id),
        )
        self.db.get_connection().commit()
