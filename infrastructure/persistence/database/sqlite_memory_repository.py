from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from domain.memory.entities import (
    MemoryAtom,
    MemoryCalibrationAction,
    MemoryProjection,
    NarrativeEntity,
)
from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteNarrativeMemoryRepository:
    """SQLite repository for the narrative memory substrate."""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def upsert_entity(self, entity: NarrativeEntity) -> NarrativeEntity:
        self.db.execute(
            """
            INSERT INTO narrative_entities
            (id, novel_id, entity_type, canonical_name, aliases_json, lifecycle_status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                novel_id=excluded.novel_id,
                entity_type=excluded.entity_type,
                canonical_name=excluded.canonical_name,
                aliases_json=excluded.aliases_json,
                lifecycle_status=excluded.lifecycle_status,
                updated_at=datetime('now')
            """,
            (
                entity.id,
                entity.novel_id,
                entity.entity_type,
                entity.canonical_name,
                json.dumps(entity.aliases, ensure_ascii=False),
                entity.lifecycle_status,
            ),
        )
        self.db.get_connection().commit()
        return entity

    def upsert_atom(self, atom: MemoryAtom) -> MemoryAtom:
        existing = self.db.fetch_one(
            """
            SELECT id FROM memory_atoms
            WHERE novel_id = ? AND entity_id = ? AND memory_type = ? AND source = ?
              AND IFNULL(chapter_number, -1) = IFNULL(?, -1) AND text_span = ?
            """,
            (
                atom.novel_id,
                atom.entity_id,
                atom.memory_type,
                atom.source,
                atom.chapter_number,
                atom.text_span,
            ),
        )
        if existing:
            atom.id = str(existing["id"])
            self.db.execute(
                """
                UPDATE memory_atoms
                SET entity_type = ?, scope = ?, status = ?, payload_json = ?,
                    confidence = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    atom.entity_type,
                    atom.scope,
                    atom.status,
                    json.dumps(atom.payload, ensure_ascii=False),
                    atom.confidence,
                    atom.id,
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO memory_atoms
                (id, novel_id, entity_id, entity_type, memory_type, scope, source, status,
                 payload_json, chapter_number, text_span, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    atom.id,
                    atom.novel_id,
                    atom.entity_id,
                    atom.entity_type,
                    atom.memory_type,
                    atom.scope,
                    atom.source,
                    atom.status,
                    json.dumps(atom.payload, ensure_ascii=False),
                    atom.chapter_number,
                    atom.text_span,
                    atom.confidence,
                ),
            )
        self.db.get_connection().commit()
        return atom

    def get_atoms_for_entity(
        self,
        novel_id: str,
        entity_id: str,
        *,
        statuses: Optional[List[str]] = None,
    ) -> List[MemoryAtom]:
        params: List[Any] = [novel_id, entity_id]
        status_clause = ""
        if statuses:
            status_clause = "AND status IN ({})".format(",".join("?" * len(statuses)))
            params.extend(statuses)
        rows = self.db.fetch_all(
            f"""
            SELECT * FROM memory_atoms
            WHERE novel_id = ? AND entity_id = ? {status_clause}
            ORDER BY COALESCE(chapter_number, 0) DESC, updated_at DESC
            """,
            tuple(params),
        )
        return [self._row_to_atom(r) for r in rows]

    def get_candidates_for_chapter(self, novel_id: str, chapter_number: int) -> List[MemoryAtom]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM memory_atoms
            WHERE novel_id = ? AND chapter_number = ? AND status = 'candidate'
            ORDER BY confidence DESC, updated_at DESC
            """,
            (novel_id, chapter_number),
        )
        return [self._row_to_atom(r) for r in rows]

    def get_atom(self, novel_id: str, atom_id: str) -> Optional[MemoryAtom]:
        row = self.db.fetch_one(
            "SELECT * FROM memory_atoms WHERE novel_id = ? AND id = ?",
            (novel_id, atom_id),
        )
        return self._row_to_atom(row) if row else None

    def update_atom_status(
        self,
        novel_id: str,
        atom_id: str,
        status: str,
        *,
        action: Optional[str] = None,
        note: str = "",
    ) -> Optional[MemoryAtom]:
        self.db.execute(
            "UPDATE memory_atoms SET status = ?, updated_at = datetime('now') WHERE novel_id = ? AND id = ?",
            (status, novel_id, atom_id),
        )
        if action:
            act = MemoryCalibrationAction(novel_id=novel_id, atom_id=atom_id, action=action, note=note)
            self.db.execute(
                """
                INSERT INTO memory_calibration_actions (id, novel_id, atom_id, action, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (act.id, act.novel_id, act.atom_id, act.action, act.note),
            )
        self.db.get_connection().commit()
        return self.get_atom(novel_id, atom_id)

    def save_projection(self, projection: MemoryProjection) -> MemoryProjection:
        self.db.execute(
            """
            INSERT OR REPLACE INTO memory_projections
            (novel_id, entity_id, entity_type, projection_type, version, projection_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                projection.novel_id,
                projection.entity_id,
                projection.entity_type,
                projection.projection_type,
                projection.version,
                json.dumps(projection.data, ensure_ascii=False),
            ),
        )
        self.db.get_connection().commit()
        return projection

    def get_projection(
        self,
        novel_id: str,
        entity_id: str,
        projection_type: str = "character",
    ) -> Optional[MemoryProjection]:
        row = self.db.fetch_one(
            """
            SELECT * FROM memory_projections
            WHERE novel_id = ? AND entity_id = ? AND projection_type = ?
            """,
            (novel_id, entity_id, projection_type),
        )
        if not row:
            return None
        return MemoryProjection(
            novel_id=row["novel_id"],
            entity_id=row["entity_id"],
            entity_type=row.get("entity_type", "character"),
            projection_type=row.get("projection_type", projection_type),
            version=int(row.get("version", 1) or 1),
            data=json.loads(row.get("projection_json") or "{}"),
        )

    @staticmethod
    def _row_to_atom(row: Dict[str, Any]) -> MemoryAtom:
        return MemoryAtom(
            id=row["id"],
            novel_id=row["novel_id"],
            entity_id=row["entity_id"],
            entity_type=row.get("entity_type", "character"),
            memory_type=row.get("memory_type", "fact"),
            scope=row.get("scope", "global"),
            source=row.get("source", "manual"),
            status=row.get("status", "candidate"),
            payload=json.loads(row.get("payload_json") or "{}"),
            chapter_number=row.get("chapter_number"),
            text_span=row.get("text_span", ""),
            confidence=float(row.get("confidence", 0.5) or 0.5),
        )
