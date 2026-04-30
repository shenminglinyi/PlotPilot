"""SQLite 写作手法知识库仓储。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from domain.style_bible.entities import (
    StyleProfile,
    StyleSample,
    StyleSampleChunk,
    StyleTechniqueCard,
)
from domain.style_bible.repositories import StyleBibleRepository
from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteStyleBibleRepository(StyleBibleRepository):
    """SQLite StyleBibleRepository 实现。"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save_sample(
        self,
        sample: StyleSample,
        chunks: list[StyleSampleChunk],
    ) -> StyleSample:
        existing = self._find_sample_by_hash(sample.novel_id, sample.content_hash)
        if existing is not None:
            return existing

        self.db.execute(
            """
            INSERT INTO style_samples (
                id, novel_id, profile_id, title, source_type, genre, scene_type,
                pov, content, content_hash, char_count, allowed_for_generation,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._sample_params(sample),
        )
        if chunks:
            self.db.execute_many(
                """
                INSERT INTO style_sample_chunks (
                    id, sample_id, chunk_type, sequence, chapter_number, title,
                    content, char_count, metrics_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    sample_id = excluded.sample_id,
                    chunk_type = excluded.chunk_type,
                    sequence = excluded.sequence,
                    chapter_number = excluded.chapter_number,
                    title = excluded.title,
                    content = excluded.content,
                    char_count = excluded.char_count,
                    metrics_json = excluded.metrics_json
                """,
                [self._chunk_params(chunk) for chunk in chunks],
            )
        self.db.commit()
        return self.get_sample(sample.id) or sample

    def list_samples(
        self,
        novel_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> list[StyleSample]:
        clauses: list[str] = []
        params: list[Any] = []
        if novel_id:
            clauses.append("novel_id = ?")
            params.append(novel_id)
        if profile_id:
            clauses.append("profile_id = ?")
            params.append(profile_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.fetch_all(
            f"""
            SELECT * FROM style_samples
            {where_sql}
            ORDER BY created_at DESC, id DESC
            """,
            tuple(params),
        )
        return [self._row_to_sample(row) for row in rows]

    def get_sample(self, sample_id: str) -> Optional[StyleSample]:
        row = self.db.fetch_one("SELECT * FROM style_samples WHERE id = ?", (sample_id,))
        return self._row_to_sample(row) if row else None

    def save_profile(self, profile: StyleProfile) -> StyleProfile:
        self.db.execute(
            """
            INSERT INTO style_profiles (
                id, novel_id, name, description, status, profile_json,
                metrics_json, rules_json, forbidden_patterns_json,
                version, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                novel_id = excluded.novel_id,
                name = excluded.name,
                description = excluded.description,
                status = excluded.status,
                profile_json = excluded.profile_json,
                metrics_json = excluded.metrics_json,
                rules_json = excluded.rules_json,
                forbidden_patterns_json = excluded.forbidden_patterns_json,
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            self._profile_params(profile),
        )
        self.db.commit()
        return self.get_profile(profile.id) or profile

    def list_profiles(
        self,
        novel_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[StyleProfile]:
        clauses: list[str] = []
        params: list[Any] = []
        if novel_id:
            clauses.append("novel_id = ?")
            params.append(novel_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.fetch_all(
            f"""
            SELECT * FROM style_profiles
            {where_sql}
            ORDER BY updated_at DESC, id DESC
            """,
            tuple(params),
        )
        return [self._row_to_profile(row) for row in rows]

    def get_profile(self, profile_id: str) -> Optional[StyleProfile]:
        row = self.db.fetch_one(
            "SELECT * FROM style_profiles WHERE id = ?",
            (profile_id,),
        )
        return self._row_to_profile(row) if row else None

    def save_technique_cards(
        self,
        profile_id: str,
        cards: list[StyleTechniqueCard],
    ) -> list[StyleTechniqueCard]:
        normalized = [
            card if card.profile_id == profile_id else self._with_profile_id(card, profile_id)
            for card in cards
        ]
        if normalized:
            self.db.execute_many(
                """
                INSERT INTO style_technique_cards (
                    id, profile_id, title, category, scene_type, rule_text,
                    example_summary, prompt_instruction, enabled, weight,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    title = excluded.title,
                    category = excluded.category,
                    scene_type = excluded.scene_type,
                    rule_text = excluded.rule_text,
                    example_summary = excluded.example_summary,
                    prompt_instruction = excluded.prompt_instruction,
                    enabled = excluded.enabled,
                    weight = excluded.weight,
                    updated_at = excluded.updated_at
                """,
                [self._card_params(card) for card in normalized],
            )
            self.db.commit()
        return [card for card in self.list_technique_cards(profile_id) if card.id in {c.id for c in normalized}]

    def list_technique_cards(
        self,
        profile_id: str,
        enabled: Optional[bool] = None,
    ) -> list[StyleTechniqueCard]:
        if enabled is None:
            rows = self.db.fetch_all(
                """
                SELECT * FROM style_technique_cards
                WHERE profile_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (profile_id,),
            )
        else:
            rows = self.db.fetch_all(
                """
                SELECT * FROM style_technique_cards
                WHERE profile_id = ? AND enabled = ?
                ORDER BY created_at ASC, id ASC
                """,
                (profile_id, 1 if enabled else 0),
            )
        return [self._row_to_card(row) for row in rows]

    def update_technique_card(self, card: StyleTechniqueCard) -> StyleTechniqueCard:
        self.db.execute(
            """
            UPDATE style_technique_cards
            SET
                title = ?,
                category = ?,
                scene_type = ?,
                rule_text = ?,
                example_summary = ?,
                prompt_instruction = ?,
                enabled = ?,
                weight = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                card.title,
                card.category,
                card.scene_type,
                card.rule_text,
                card.example_summary,
                card.prompt_instruction,
                1 if card.enabled else 0,
                card.weight,
                self._dt(card.updated_at),
                card.id,
            ),
        )
        self.db.commit()
        row = self.db.fetch_one("SELECT * FROM style_technique_cards WHERE id = ?", (card.id,))
        return self._row_to_card(row) if row else card

    def _find_sample_by_hash(
        self,
        novel_id: str,
        content_hash: str,
    ) -> Optional[StyleSample]:
        row = self.db.fetch_one(
            """
            SELECT * FROM style_samples
            WHERE novel_id = ? AND content_hash = ?
            """,
            (novel_id, content_hash),
        )
        return self._row_to_sample(row) if row else None

    @staticmethod
    def _with_profile_id(
        card: StyleTechniqueCard,
        profile_id: str,
    ) -> StyleTechniqueCard:
        return StyleTechniqueCard(
            id=card.id,
            profile_id=profile_id,
            title=card.title,
            category=card.category,
            scene_type=card.scene_type,
            rule_text=card.rule_text,
            example_summary=card.example_summary,
            prompt_instruction=card.prompt_instruction,
            enabled=card.enabled,
            weight=card.weight,
            created_at=card.created_at,
            updated_at=card.updated_at,
        )

    @staticmethod
    def _dump_json(value: Any, fallback: Any) -> str:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)

    @staticmethod
    def _load_json_dict(value: Any) -> dict[str, Any]:
        if not value:
            return {}
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _load_json_list(value: Any) -> list[Any]:
        if not value:
            return []
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _parse_dt(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if value:
            try:
                return datetime.fromisoformat(str(value))
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _dt(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value or datetime.now(timezone.utc).isoformat())

    def _sample_params(self, sample: StyleSample) -> tuple[Any, ...]:
        return (
            sample.id,
            sample.novel_id,
            sample.profile_id,
            sample.title,
            sample.source_type,
            sample.genre,
            sample.scene_type,
            sample.pov,
            sample.content,
            sample.content_hash,
            sample.char_count,
            1 if sample.allowed_for_generation else 0,
            self._dt(sample.created_at),
            self._dt(sample.updated_at),
        )

    def _chunk_params(self, chunk: StyleSampleChunk) -> tuple[Any, ...]:
        return (
            chunk.id,
            chunk.sample_id,
            chunk.chunk_type,
            chunk.sequence,
            chunk.chapter_number,
            chunk.title,
            chunk.content,
            chunk.char_count,
            self._dump_json(chunk.metrics, {}),
            self._dt(chunk.created_at),
        )

    def _profile_params(self, profile: StyleProfile) -> tuple[Any, ...]:
        return (
            profile.id,
            profile.novel_id,
            profile.name,
            profile.description,
            profile.status,
            self._dump_json(profile.profile, {}),
            self._dump_json(profile.metrics, {}),
            self._dump_json(profile.rules, []),
            self._dump_json(profile.forbidden_patterns, []),
            profile.version,
            self._dt(profile.created_at),
            self._dt(profile.updated_at),
        )

    def _card_params(self, card: StyleTechniqueCard) -> tuple[Any, ...]:
        return (
            card.id,
            card.profile_id,
            card.title,
            card.category,
            card.scene_type,
            card.rule_text,
            card.example_summary,
            card.prompt_instruction,
            1 if card.enabled else 0,
            card.weight,
            self._dt(card.created_at),
            self._dt(card.updated_at),
        )

    def _row_to_sample(self, row: dict[str, Any]) -> StyleSample:
        return StyleSample(
            id=row["id"],
            novel_id=row.get("novel_id") or "",
            profile_id=row.get("profile_id") or "",
            title=row["title"],
            source_type=row.get("source_type") or "reference",
            genre=row.get("genre") or "",
            scene_type=row.get("scene_type") or "",
            pov=row.get("pov") or "",
            content=row["content"],
            content_hash=row.get("content_hash") or "",
            char_count=int(row.get("char_count") or 0),
            allowed_for_generation=bool(row.get("allowed_for_generation")),
            created_at=self._parse_dt(row.get("created_at")),
            updated_at=self._parse_dt(row.get("updated_at")),
        )

    def _row_to_profile(self, row: dict[str, Any]) -> StyleProfile:
        return StyleProfile(
            id=row["id"],
            novel_id=row.get("novel_id") or "",
            name=row["name"],
            description=row.get("description") or "",
            status=row.get("status") or "active",
            profile=self._load_json_dict(row.get("profile_json")),
            metrics=self._load_json_dict(row.get("metrics_json")),
            rules=self._load_json_list(row.get("rules_json")),
            forbidden_patterns=self._load_json_list(row.get("forbidden_patterns_json")),
            version=int(row.get("version") or 1),
            created_at=self._parse_dt(row.get("created_at")),
            updated_at=self._parse_dt(row.get("updated_at")),
        )

    def _row_to_card(self, row: dict[str, Any]) -> StyleTechniqueCard:
        return StyleTechniqueCard(
            id=row["id"],
            profile_id=row.get("profile_id") or "",
            title=row["title"],
            category=row.get("category") or "",
            scene_type=row.get("scene_type") or "",
            rule_text=row.get("rule_text") or "",
            example_summary=row.get("example_summary") or "",
            prompt_instruction=row.get("prompt_instruction") or "",
            enabled=bool(row.get("enabled")),
            weight=float(row.get("weight") or 1.0),
            created_at=self._parse_dt(row.get("created_at")),
            updated_at=self._parse_dt(row.get("updated_at")),
        )
