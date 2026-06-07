from __future__ import annotations

import json
from typing import Any

from application.governance.models import (
    CanonicalStoryline,
    GovernanceIssue,
    GovernanceReport,
    NarrativeContract,
)
from infrastructure.persistence.database.connection import DatabaseConnection


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _loads(text: str | None, fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


class SqliteGovernanceRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.ensure_schema()

    def _execute_write(self, sql: str, params: tuple = ()) -> None:
        conn = self.db.get_connection()
        conn.execute(sql, params)
        conn.commit()

    def ensure_schema(self) -> None:
        conn = self.db.get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS narrative_contracts (
                novel_id TEXT PRIMARY KEY,
                title_promise TEXT NOT NULL DEFAULT '',
                core_question TEXT NOT NULL DEFAULT '',
                theme_anchors_json TEXT NOT NULL DEFAULT '[]',
                forbidden_early_payoffs_json TEXT NOT NULL DEFAULT '[]',
                reveal_budget_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_storylines (
                canonical_id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                canonical_key TEXT NOT NULL,
                title TEXT NOT NULL,
                aliases_json TEXT NOT NULL DEFAULT '[]',
                goal TEXT NOT NULL DEFAULT '',
                conflict TEXT NOT NULL DEFAULT '',
                span_json TEXT NOT NULL DEFAULT '{}',
                promise_tags_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                source_storyline_ids_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_id, canonical_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS governance_reports (
                report_id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                severity TEXT NOT NULL,
                promise_hit_rate REAL NOT NULL DEFAULT 0,
                issues_json TEXT NOT NULL DEFAULT '[]',
                budget_patch_json TEXT NOT NULL DEFAULT '{}',
                should_pause_autopilot INTEGER NOT NULL DEFAULT 0,
                review_status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS governance_events (
                event_id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                chapter_number INTEGER,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_canonical_storylines_novel ON canonical_storylines(novel_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_governance_reports_novel_chapter ON governance_reports(novel_id, chapter_number)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_governance_events_novel ON governance_events(novel_id, created_at)"
        )
        conn.commit()

    def get_contract(self, novel_id: str) -> NarrativeContract | None:
        row = self.db.fetch_one("SELECT * FROM narrative_contracts WHERE novel_id = ?", (novel_id,))
        if not row:
            return None
        return NarrativeContract(
            novel_id=row["novel_id"],
            title_promise=row["title_promise"] or "",
            core_question=row["core_question"] or "",
            theme_anchors=list(_loads(row["theme_anchors_json"], [])),
            forbidden_early_payoffs=list(_loads(row["forbidden_early_payoffs_json"], [])),
            reveal_budget=dict(_loads(row["reveal_budget_json"], {})),
            updated_at=row["updated_at"],
        )

    def save_contract(self, contract: NarrativeContract) -> None:
        self._execute_write(
            """
            INSERT INTO narrative_contracts (
                novel_id, title_promise, core_question, theme_anchors_json,
                forbidden_early_payoffs_json, reveal_budget_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(novel_id) DO UPDATE SET
                title_promise = excluded.title_promise,
                core_question = excluded.core_question,
                theme_anchors_json = excluded.theme_anchors_json,
                forbidden_early_payoffs_json = excluded.forbidden_early_payoffs_json,
                reveal_budget_json = excluded.reveal_budget_json,
                updated_at = excluded.updated_at
            """,
            (
                contract.novel_id,
                contract.title_promise,
                contract.core_question,
                _json(contract.theme_anchors),
                _json(contract.forbidden_early_payoffs),
                _json(contract.reveal_budget),
                contract.updated_at,
            ),
        )

    def list_storylines(self, novel_id: str) -> list[CanonicalStoryline]:
        rows = self.db.fetch_all(
            "SELECT * FROM canonical_storylines WHERE novel_id = ? ORDER BY status, title",
            (novel_id,),
        )
        return [self._row_to_storyline(row) for row in rows]

    def upsert_storyline(self, storyline: CanonicalStoryline) -> None:
        self._execute_write(
            """
            INSERT INTO canonical_storylines (
                canonical_id, novel_id, canonical_key, title, aliases_json,
                goal, conflict, span_json, promise_tags_json, status,
                source_storyline_ids_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_id) DO UPDATE SET
                canonical_key = excluded.canonical_key,
                title = excluded.title,
                aliases_json = excluded.aliases_json,
                goal = excluded.goal,
                conflict = excluded.conflict,
                span_json = excluded.span_json,
                promise_tags_json = excluded.promise_tags_json,
                status = excluded.status,
                source_storyline_ids_json = excluded.source_storyline_ids_json,
                updated_at = excluded.updated_at
            """,
            (
                storyline.canonical_id,
                storyline.novel_id,
                storyline.canonical_key,
                storyline.title,
                _json(storyline.aliases),
                storyline.goal,
                storyline.conflict,
                _json(storyline.span),
                _json(storyline.promise_tags),
                storyline.status,
                _json(storyline.source_storyline_ids),
                storyline.updated_at,
            ),
        )

    def get_storyline(self, canonical_id: str) -> CanonicalStoryline | None:
        row = self.db.fetch_one(
            "SELECT * FROM canonical_storylines WHERE canonical_id = ?",
            (canonical_id,),
        )
        return self._row_to_storyline(row) if row else None

    def delete_storyline(self, canonical_id: str) -> None:
        self._execute_write("DELETE FROM canonical_storylines WHERE canonical_id = ?", (canonical_id,))

    def save_report(self, report: GovernanceReport) -> None:
        self._execute_write(
            """
            INSERT INTO governance_reports (
                report_id, novel_id, chapter_number, severity, promise_hit_rate,
                issues_json, budget_patch_json, should_pause_autopilot,
                review_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                severity = excluded.severity,
                promise_hit_rate = excluded.promise_hit_rate,
                issues_json = excluded.issues_json,
                budget_patch_json = excluded.budget_patch_json,
                should_pause_autopilot = excluded.should_pause_autopilot,
                review_status = excluded.review_status
            """,
            (
                report.report_id,
                report.novel_id,
                report.chapter_number,
                report.severity,
                report.promise_hit_rate,
                _json([issue.to_dict() for issue in report.issues]),
                _json(report.budget_patch),
                1 if report.should_pause_autopilot else 0,
                report.review_status,
                report.created_at,
            ),
        )

    def latest_report(self, novel_id: str) -> GovernanceReport | None:
        row = self.db.fetch_one(
            """
            SELECT * FROM governance_reports
            WHERE novel_id = ?
            ORDER BY chapter_number DESC, created_at DESC
            LIMIT 1
            """,
            (novel_id,),
        )
        return self._row_to_report(row) if row else None

    def update_report_status(self, novel_id: str, report_id: str, status: str) -> None:
        self._execute_write(
            "UPDATE governance_reports SET review_status = ? WHERE novel_id = ? AND report_id = ?",
            (status, novel_id, report_id),
        )

    def append_event(
        self,
        event_id: str,
        novel_id: str,
        event_type: str,
        chapter_number: int | None,
        payload: dict[str, Any],
    ) -> None:
        self._execute_write(
            """
            INSERT INTO governance_events (event_id, novel_id, event_type, chapter_number, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, novel_id, event_type, chapter_number, _json(payload)),
        )

    def list_open_debts(self, novel_id: str, limit: int = 50) -> list[dict[str, Any]]:
        try:
            rows = self.db.fetch_all(
                """
                SELECT * FROM narrative_debts
                WHERE novel_id = ? AND COALESCE(status, 'open') NOT IN ('closed', 'resolved')
                ORDER BY COALESCE(due_chapter, 999999), rowid DESC
                LIMIT ?
                """,
                (novel_id, limit),
            )
        except Exception:
            return []
        return [dict(row) for row in rows]

    def _row_to_storyline(self, row: dict[str, Any]) -> CanonicalStoryline:
        return CanonicalStoryline(
            canonical_id=row["canonical_id"],
            novel_id=row["novel_id"],
            canonical_key=row["canonical_key"],
            title=row["title"],
            aliases=list(_loads(row["aliases_json"], [])),
            goal=row["goal"] or "",
            conflict=row["conflict"] or "",
            span=dict(_loads(row["span_json"], {})),
            promise_tags=list(_loads(row["promise_tags_json"], [])),
            status=row["status"] or "active",
            source_storyline_ids=list(_loads(row["source_storyline_ids_json"], [])),
            updated_at=row["updated_at"],
        )

    def _row_to_report(self, row: dict[str, Any]) -> GovernanceReport:
        issues = []
        for raw in _loads(row["issues_json"], []):
            if isinstance(raw, dict):
                issues.append(GovernanceIssue(**raw))
        return GovernanceReport(
            report_id=row["report_id"],
            novel_id=row["novel_id"],
            chapter_number=int(row["chapter_number"] or 0),
            severity=row["severity"],
            promise_hit_rate=float(row["promise_hit_rate"] or 0),
            issues=issues,
            budget_patch=dict(_loads(row["budget_patch_json"], {})),
            should_pause_autopilot=bool(row["should_pause_autopilot"]),
            created_at=row["created_at"],
            review_status=row["review_status"] or "open",
        )
