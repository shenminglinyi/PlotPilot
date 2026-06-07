from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from domain.evolution.models import ChapterEvolutionSnapshot, EvolutionAction, EvolutionState, utcnow_iso


def _json_loads(value: Any, fallback: Any):
    if value is None or value == "":
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


class SqliteEvolutionRepository:
    def __init__(self, db):
        self.db = db

    def save(self, snapshot: ChapterEvolutionSnapshot) -> None:
        data = snapshot.to_dict()
        self.db.execute(
            """
            INSERT INTO chapter_evolution_snapshots (
                snapshot_id, novel_id, branch_id, chapter_number, schema_version, status,
                opening_state_json, delta_actions_json, machine_state_json,
                override_patches_json, ending_state_json, source_refs_json, conflicts_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                status=excluded.status,
                opening_state_json=excluded.opening_state_json,
                delta_actions_json=excluded.delta_actions_json,
                machine_state_json=excluded.machine_state_json,
                override_patches_json=excluded.override_patches_json,
                ending_state_json=excluded.ending_state_json,
                source_refs_json=excluded.source_refs_json,
                conflicts_json=excluded.conflicts_json,
                updated_at=excluded.updated_at
            """,
            (
                data["snapshot_id"],
                data["novel_id"],
                data["branch_id"],
                data["chapter_number"],
                data["schema_version"],
                data["status"],
                json.dumps(data["opening_state"], ensure_ascii=False),
                json.dumps(data["delta_actions"], ensure_ascii=False),
                json.dumps(data["machine_state"], ensure_ascii=False),
                json.dumps(data["human_override_patches"], ensure_ascii=False),
                json.dumps(data["ending_state"], ensure_ascii=False),
                json.dumps(data["source_refs"], ensure_ascii=False),
                json.dumps(data["conflicts"], ensure_ascii=False),
                data["created_at"],
                data["updated_at"],
            ),
        )
        for action in snapshot.delta_actions:
            self.db.execute(
                """
                INSERT OR IGNORE INTO chapter_evolution_action_log (
                    action_id, snapshot_id, novel_id, branch_id, chapter_number,
                    action_type, payload_json, source_ref_json, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.action_id,
                    snapshot.snapshot_id,
                    snapshot.novel_id,
                    snapshot.branch_id,
                    snapshot.chapter_number,
                    action.type,
                    json.dumps(action.payload, ensure_ascii=False),
                    json.dumps(action.source_refs, ensure_ascii=False),
                    action.confidence,
                    utcnow_iso(),
                ),
            )
        for conflict in snapshot.conflicts:
            self._insert_conflict(snapshot, conflict)
        self.db.get_connection().commit()

    def list_snapshots(
        self,
        novel_id: str,
        branch_id: str = "main",
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[ChapterEvolutionSnapshot]:
        sql = """
            SELECT * FROM chapter_evolution_snapshots
            WHERE novel_id = ? AND branch_id = ?
        """
        params: list[Any] = [novel_id, branch_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY chapter_number DESC LIMIT ?"
        params.append(limit)
        return [self._row_to_snapshot(r) for r in self.db.fetch_all(sql, tuple(params))]

    def get_by_id(self, snapshot_id: str) -> Optional[ChapterEvolutionSnapshot]:
        row = self.db.fetch_one(
            "SELECT * FROM chapter_evolution_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        return self._row_to_snapshot(row) if row else None

    def get_by_chapter(
        self,
        novel_id: str,
        branch_id: str,
        chapter_number: int,
    ) -> Optional[ChapterEvolutionSnapshot]:
        row = self.db.fetch_one(
            """
            SELECT * FROM chapter_evolution_snapshots
            WHERE novel_id = ? AND branch_id = ? AND chapter_number = ? AND status != 'stale'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (novel_id, branch_id, chapter_number),
        )
        return self._row_to_snapshot(row) if row else None

    def get_latest_active_before(
        self,
        novel_id: str,
        branch_id: str,
        chapter_number: int,
    ) -> Optional[ChapterEvolutionSnapshot]:
        row = self.db.fetch_one(
            """
            SELECT * FROM chapter_evolution_snapshots
            WHERE novel_id = ? AND branch_id = ? AND chapter_number < ? AND status = 'active'
            ORDER BY chapter_number DESC, updated_at DESC LIMIT 1
            """,
            (novel_id, branch_id, chapter_number),
        )
        return self._row_to_snapshot(row) if row else None

    def get_latest_active(self, novel_id: str, branch_id: str = "main") -> Optional[ChapterEvolutionSnapshot]:
        row = self.db.fetch_one(
            """
            SELECT * FROM chapter_evolution_snapshots
            WHERE novel_id = ? AND branch_id = ? AND status = 'active'
            ORDER BY chapter_number DESC, updated_at DESC LIMIT 1
            """,
            (novel_id, branch_id),
        )
        return self._row_to_snapshot(row) if row else None

    def mark_stale_from(self, novel_id: str, branch_id: str, chapter_number: int) -> int:
        rows = self.db.fetch_all(
            """
            SELECT snapshot_id FROM chapter_evolution_snapshots
            WHERE novel_id = ? AND branch_id = ? AND chapter_number >= ? AND status != 'stale'
            """,
            (novel_id, branch_id, chapter_number),
        )
        self.db.execute(
            """
            UPDATE chapter_evolution_snapshots
            SET status = 'stale', updated_at = ?
            WHERE novel_id = ? AND branch_id = ? AND chapter_number >= ? AND status != 'stale'
            """,
            (utcnow_iso(), novel_id, branch_id, chapter_number),
        )
        self.db.get_connection().commit()
        return len(rows)

    def mark_blocked(self, snapshot_id: str, conflicts: List[Dict[str, Any]]) -> None:
        current = self.get_by_id(snapshot_id)
        merged = list(current.conflicts if current else []) + list(conflicts or [])
        self.db.execute(
            """
            UPDATE chapter_evolution_snapshots
            SET status='blocked', conflicts_json=?, updated_at=?
            WHERE snapshot_id=?
            """,
            (json.dumps(merged, ensure_ascii=False), utcnow_iso(), snapshot_id),
        )
        if current:
            for conflict in conflicts or []:
                self._insert_conflict(current, conflict)
        self.db.get_connection().commit()

    def update_overrides(
        self,
        snapshot_id: str,
        patches: List[Dict[str, Any]],
        ending_state: Dict[str, Any],
    ) -> None:
        self.db.execute(
            """
            UPDATE chapter_evolution_snapshots
            SET status='active', override_patches_json=?, ending_state_json=?, updated_at=?
            WHERE snapshot_id=?
            """,
            (
                json.dumps(patches or [], ensure_ascii=False),
                json.dumps(ending_state or {}, ensure_ascii=False),
                utcnow_iso(),
                snapshot_id,
            ),
        )
        self.db.get_connection().commit()

    def count_by_status(self, novel_id: str, branch_id: str = "main") -> Dict[str, int]:
        rows = self.db.fetch_all(
            """
            SELECT status, COUNT(*) AS c FROM chapter_evolution_snapshots
            WHERE novel_id = ? AND branch_id = ?
            GROUP BY status
            """,
            (novel_id, branch_id),
        )
        return {str(r["status"]): int(r["c"]) for r in rows}

    def update_conflict_resolution(self, conflict_id: str, resolution_status: str) -> bool:
        existing = self.db.fetch_one(
            "SELECT conflict_id FROM chapter_evolution_conflicts WHERE conflict_id = ?",
            (conflict_id,),
        )
        if not existing:
            return False
        self.db.execute(
            "UPDATE chapter_evolution_conflicts SET resolution_status=?, resolved_at=? WHERE conflict_id=?",
            (resolution_status, utcnow_iso(), conflict_id),
        )
        self.db.get_connection().commit()
        return True

    def _insert_conflict(self, snapshot: ChapterEvolutionSnapshot, conflict: Dict[str, Any]) -> None:
        import uuid

        conflict_id = conflict.get("conflict_id") or str(uuid.uuid4())
        self.db.execute(
            """
            INSERT OR IGNORE INTO chapter_evolution_conflicts (
                conflict_id, snapshot_id, novel_id, branch_id, chapter_number,
                conflict_type, level, message, payload_json, resolution_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conflict_id,
                snapshot.snapshot_id,
                snapshot.novel_id,
                snapshot.branch_id,
                snapshot.chapter_number,
                conflict.get("conflict_type") or conflict.get("type") or "REDUCER_ERROR",
                conflict.get("level") or "blocking",
                conflict.get("message") or "",
                json.dumps(conflict, ensure_ascii=False),
                conflict.get("resolution_status") or "open",
                utcnow_iso(),
            ),
        )

    @staticmethod
    def _row_to_snapshot(row: Dict[str, Any]) -> ChapterEvolutionSnapshot:
        actions = [
            EvolutionAction.from_dict(a)
            for a in _json_loads(row.get("delta_actions_json"), [])
        ]
        return ChapterEvolutionSnapshot(
            snapshot_id=row["snapshot_id"],
            novel_id=row["novel_id"],
            branch_id=row.get("branch_id") or "main",
            chapter_number=int(row["chapter_number"]),
            schema_version=row.get("schema_version") or "v2.0",
            status=row.get("status") or "active",
            opening_state=EvolutionState.from_dict(_json_loads(row.get("opening_state_json"), {})),
            delta_actions=actions,
            machine_state=EvolutionState.from_dict(_json_loads(row.get("machine_state_json"), {})),
            human_override_patches=_json_loads(row.get("override_patches_json"), []),
            ending_state=EvolutionState.from_dict(_json_loads(row.get("ending_state_json"), {})),
            source_refs=_json_loads(row.get("source_refs_json"), []),
            conflicts=_json_loads(row.get("conflicts_json"), []),
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
        )
