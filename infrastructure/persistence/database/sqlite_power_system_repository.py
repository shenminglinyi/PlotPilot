"""SQLite repository for NovelPro power-system tracking."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from infrastructure.persistence.database.connection import DatabaseConnection


class SqlitePowerSystemRepository:
    """战力规则、角色档案与战斗事件台账。"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_rules(self, novel_id: str) -> Optional[dict[str, Any]]:
        return self.db.fetch_one(
            "SELECT * FROM power_system_rules WHERE novel_id = ?",
            (novel_id,),
        )

    def upsert_rules(
        self,
        *,
        novel_id: str,
        genre_type: str,
        tier_schema: str,
        core_rules: str,
        taboo_rules: str,
        escalation_rules: str,
    ) -> dict[str, Any]:
        existing = self.get_rules(novel_id)
        now = datetime.utcnow().isoformat()
        if existing:
            self.db.execute(
                """
                UPDATE power_system_rules
                SET genre_type = ?, tier_schema = ?, core_rules = ?,
                    taboo_rules = ?, escalation_rules = ?, updated_at = ?
                WHERE novel_id = ?
                """,
                (
                    genre_type,
                    tier_schema,
                    core_rules,
                    taboo_rules,
                    escalation_rules,
                    now,
                    novel_id,
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO power_system_rules (
                    id, novel_id, genre_type, tier_schema, core_rules,
                    taboo_rules, escalation_rules, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    novel_id,
                    genre_type,
                    tier_schema,
                    core_rules,
                    taboo_rules,
                    escalation_rules,
                    now,
                    now,
                ),
            )
        self.db.commit()
        return self.get_rules(novel_id) or {}

    def list_profiles(self, novel_id: str) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT * FROM power_character_profiles
            WHERE novel_id = ?
            ORDER BY rank_score DESC, character_name ASC
            """,
            (novel_id,),
        )

    def upsert_profile(
        self,
        *,
        novel_id: str,
        character_name: str,
        tier: str,
        rank_score: int,
        abilities: str,
        limitations: str,
        growth_stage: str,
        last_verified_chapter: Optional[int],
        notes: str,
    ) -> dict[str, Any]:
        existing = self.db.fetch_one(
            """
            SELECT * FROM power_character_profiles
            WHERE novel_id = ? AND character_name = ?
            """,
            (novel_id, character_name),
        )
        now = datetime.utcnow().isoformat()
        if existing:
            self.db.execute(
                """
                UPDATE power_character_profiles
                SET tier = ?, rank_score = ?, abilities = ?, limitations = ?,
                    growth_stage = ?, last_verified_chapter = ?, notes = ?,
                    updated_at = ?
                WHERE novel_id = ? AND character_name = ?
                """,
                (
                    tier,
                    int(rank_score),
                    abilities,
                    limitations,
                    growth_stage,
                    last_verified_chapter,
                    notes,
                    now,
                    novel_id,
                    character_name,
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO power_character_profiles (
                    id, novel_id, character_name, tier, rank_score, abilities,
                    limitations, growth_stage, last_verified_chapter, notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    novel_id,
                    character_name,
                    tier,
                    int(rank_score),
                    abilities,
                    limitations,
                    growth_stage,
                    last_verified_chapter,
                    notes,
                    now,
                    now,
                ),
            )
        self.db.commit()
        return self.db.fetch_one(
            """
            SELECT * FROM power_character_profiles
            WHERE novel_id = ? AND character_name = ?
            """,
            (novel_id, character_name),
        ) or {}

    def list_events(
        self,
        novel_id: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT * FROM power_progression_events
            WHERE novel_id = ?
            ORDER BY chapter_number DESC, created_at DESC
            LIMIT ?
            """,
            (novel_id, int(limit)),
        )

    def create_event(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        character_name: str,
        event_type: str,
        opponent: str,
        outcome: str,
        power_delta: int,
        evidence: str,
    ) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO power_progression_events (
                id, novel_id, chapter_number, character_name, event_type,
                opponent, outcome, power_delta, evidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                novel_id,
                int(chapter_number),
                character_name,
                event_type,
                opponent,
                outcome,
                int(power_delta),
                evidence,
                now,
            ),
        )
        self.db.commit()
        return self.db.fetch_one(
            "SELECT * FROM power_progression_events WHERE id = ?",
            (event_id,),
        ) or {}
