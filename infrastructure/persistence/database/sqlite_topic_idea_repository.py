"""SQLite 选题候选仓储。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from application.topic.dtos import (
    TopicMarketSignalAutomationSettingsDTO,
    TopicMarketSignalDTO,
    TopicMarketSignalSourceCredentialDTO,
    TopicMarketSignalSourceHealthDTO,
)
from domain.topic.entities import TopicIdea, TopicIdeaStatus
from domain.topic.repositories import TopicIdeaRepository
from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteTopicIdeaRepository(TopicIdeaRepository):
    """SQLite TopicIdea Repository 实现。"""

    SETTINGS_ROW_ID = "default"

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save(self, idea: TopicIdea) -> None:
        sql = """
            INSERT INTO topic_ideas (
                id, status, title, genre, world_preset, length_tier,
                logline, premise, protagonist_hook, core_conflict, opening_hook,
                selling_points_json, long_term_potential, risk_notes_json,
                market_tags_json, score, adopted_novel_id, source_brief_json,
                development_notes_json, evaluation_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                title = excluded.title,
                genre = excluded.genre,
                world_preset = excluded.world_preset,
                length_tier = excluded.length_tier,
                logline = excluded.logline,
                premise = excluded.premise,
                protagonist_hook = excluded.protagonist_hook,
                core_conflict = excluded.core_conflict,
                opening_hook = excluded.opening_hook,
                selling_points_json = excluded.selling_points_json,
                long_term_potential = excluded.long_term_potential,
                risk_notes_json = excluded.risk_notes_json,
                market_tags_json = excluded.market_tags_json,
                score = excluded.score,
                adopted_novel_id = excluded.adopted_novel_id,
                source_brief_json = excluded.source_brief_json,
                development_notes_json = excluded.development_notes_json,
                evaluation_json = excluded.evaluation_json,
                updated_at = excluded.updated_at
        """
        self.db.execute(sql, self._params(idea))
        self.db.commit()

    def update(self, idea: TopicIdea) -> TopicIdea:
        self.save(idea)
        return self.get_by_id(idea.id) or idea

    def get_by_id(self, idea_id: str) -> Optional[TopicIdea]:
        row = self.db.fetch_one("SELECT * FROM topic_ideas WHERE id = ?", (idea_id,))
        return self._row_to_idea(row) if row else None

    def list(self, status: TopicIdeaStatus | str | None = None) -> list[TopicIdea]:
        if status:
            status_value = self._status_value(status)
            rows = self.db.fetch_all(
                "SELECT * FROM topic_ideas WHERE status = ? ORDER BY created_at DESC",
                (status_value,),
            )
        else:
            rows = self.db.fetch_all(
                "SELECT * FROM topic_ideas ORDER BY created_at DESC"
            )
        return [self._row_to_idea(row) for row in rows]

    def update_status(
        self,
        idea_id: str,
        status: TopicIdeaStatus | str,
        adopted_novel_id: Optional[str] = None,
    ) -> Optional[TopicIdea]:
        idea = self.get_by_id(idea_id)
        if idea is None:
            return None
        idea.update_status(status, adopted_novel_id)
        self.save(idea)
        return idea

    def save_market_signals(self, signals: list[TopicMarketSignalDTO]) -> None:
        new_signals = self._deduplicate_market_signals(signals)
        if not new_signals:
            return
        sql = """
            INSERT INTO topic_market_signals (
                id, source, title, genre, tags_json, summary, raw_text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source = excluded.source,
                title = excluded.title,
                genre = excluded.genre,
                tags_json = excluded.tags_json,
                summary = excluded.summary,
                raw_text = excluded.raw_text
        """
        self.db.execute_many(
            sql,
            [
                (
                    signal.id,
                    signal.source,
                    signal.title,
                    signal.genre,
                    self._dump_json(signal.tags, []),
                    signal.summary,
                    signal.raw_text,
                    signal.created_at,
                )
                for signal in new_signals
            ],
        )
        self.db.commit()

    def list_market_signals(self, limit: int = 20) -> list[TopicMarketSignalDTO]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM topic_market_signals
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 20), 500)),),
        )
        return [self._row_to_market_signal(row) for row in rows]

    def get_market_signal_settings(self) -> TopicMarketSignalAutomationSettingsDTO:
        row = self.db.fetch_one(
            "SELECT * FROM topic_market_signal_settings WHERE id = ?",
            (self.SETTINGS_ROW_ID,),
        )
        if not row:
            return TopicMarketSignalAutomationSettingsDTO()
        return self._row_to_market_signal_settings(row)

    def save_market_signal_settings(
        self,
        settings: TopicMarketSignalAutomationSettingsDTO,
    ) -> TopicMarketSignalAutomationSettingsDTO:
        sql = """
            INSERT INTO topic_market_signal_settings (
                id, enabled, interval_minutes, limit_per_source, lookback_days,
                source_weights_json, selected_source_keys_json, last_run_at,
                last_status, last_error, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                enabled = excluded.enabled,
                interval_minutes = excluded.interval_minutes,
                limit_per_source = excluded.limit_per_source,
                lookback_days = excluded.lookback_days,
                source_weights_json = excluded.source_weights_json,
                selected_source_keys_json = excluded.selected_source_keys_json,
                last_run_at = excluded.last_run_at,
                last_status = excluded.last_status,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
        """
        normalized = TopicMarketSignalAutomationSettingsDTO(
            enabled=bool(settings.enabled),
            interval_minutes=max(15, min(int(settings.interval_minutes or 180), 24 * 60)),
            limit_per_source=max(1, min(int(settings.limit_per_source or 8), 30)),
            lookback_days=max(1, min(int(settings.lookback_days or 30), 90)),
            source_weights=self._normalize_source_weights(settings.source_weights),
            selected_source_keys=self._normalize_source_keys(settings.selected_source_keys),
            last_run_at=str(settings.last_run_at or ""),
            last_status=str(settings.last_status or "idle"),
            last_error=str(settings.last_error or ""),
            updated_at=str(settings.updated_at or datetime.now(timezone.utc).isoformat()),
        )
        self.db.execute(
            sql,
            (
                self.SETTINGS_ROW_ID,
                1 if normalized.enabled else 0,
                normalized.interval_minutes,
                normalized.limit_per_source,
                normalized.lookback_days,
                self._dump_json(normalized.source_weights, {}),
                self._dump_json(normalized.selected_source_keys, []),
                normalized.last_run_at,
                normalized.last_status,
                normalized.last_error,
                normalized.updated_at,
            ),
        )
        self.db.commit()
        return normalized

    def list_market_signal_credentials(self) -> list[TopicMarketSignalSourceCredentialDTO]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM topic_market_signal_credentials
            ORDER BY source_key ASC
            """
        )
        return [self._row_to_market_signal_credentials(row) for row in rows]

    def save_market_signal_credentials(
        self,
        credentials: TopicMarketSignalSourceCredentialDTO,
    ) -> TopicMarketSignalSourceCredentialDTO:
        normalized = TopicMarketSignalSourceCredentialDTO(
            source_key=str(credentials.source_key or "").strip(),
            api_key=str(credentials.api_key or "").strip(),
            cookie=str(credentials.cookie or "").strip(),
            endpoint_url=str(credentials.endpoint_url or "").strip(),
            headers=self._normalize_headers(credentials.headers),
            updated_at=str(credentials.updated_at or datetime.now(timezone.utc).isoformat()),
        )
        self.db.execute(
            """
            INSERT INTO topic_market_signal_credentials (
                source_key, api_key, cookie, endpoint_url, headers_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                api_key = excluded.api_key,
                cookie = excluded.cookie,
                endpoint_url = excluded.endpoint_url,
                headers_json = excluded.headers_json,
                updated_at = excluded.updated_at
            """,
            (
                normalized.source_key,
                normalized.api_key,
                normalized.cookie,
                normalized.endpoint_url,
                self._dump_json(normalized.headers, {}),
                normalized.updated_at,
            ),
        )
        self.db.commit()
        return normalized

    def list_market_signal_source_health(self) -> list[TopicMarketSignalSourceHealthDTO]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM topic_market_signal_source_health
            ORDER BY source_key ASC
            """
        )
        return [self._row_to_market_signal_source_health(row) for row in rows]

    def save_market_signal_source_health(
        self,
        health: TopicMarketSignalSourceHealthDTO,
    ) -> TopicMarketSignalSourceHealthDTO:
        normalized = TopicMarketSignalSourceHealthDTO(
            source_key=str(health.source_key or "").strip(),
            source_name=str(health.source_name or "").strip(),
            status=str(health.status or "unknown").strip() or "unknown",
            last_run_at=str(health.last_run_at or ""),
            last_success_at=str(health.last_success_at or ""),
            last_count=max(0, int(health.last_count or 0)),
            last_error=str(health.last_error or ""),
            next_run_at=str(health.next_run_at or ""),
        )
        self.db.execute(
            """
            INSERT INTO topic_market_signal_source_health (
                source_key, status, last_run_at, last_success_at,
                last_count, last_error, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                status = excluded.status,
                last_run_at = excluded.last_run_at,
                last_success_at = CASE
                    WHEN excluded.last_success_at != '' THEN excluded.last_success_at
                    ELSE topic_market_signal_source_health.last_success_at
                END,
                last_count = excluded.last_count,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (
                normalized.source_key,
                normalized.status,
                normalized.last_run_at,
                normalized.last_success_at,
                normalized.last_count,
                normalized.last_error,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.db.commit()
        return normalized

    def _deduplicate_market_signals(
        self,
        signals: list[TopicMarketSignalDTO],
    ) -> list[TopicMarketSignalDTO]:
        rows = self.db.fetch_all(
            "SELECT id, source, title, summary FROM topic_market_signals"
        )
        existing_ids = {str(row.get("id") or "") for row in rows}
        title_keys = {
            self._market_signal_key(row.get("source"), row.get("title"))
            for row in rows
            if str(row.get("title") or "").strip()
        }
        summary_keys = {
            self._market_signal_key(row.get("source"), row.get("summary"))
            for row in rows
            if str(row.get("summary") or "").strip()
        }
        result: list[TopicMarketSignalDTO] = []
        for signal in signals:
            signal_id = str(signal.id or "").strip()
            source = str(signal.source or "").strip()
            title = str(signal.title or "").strip()
            summary = str(signal.summary or "").strip()
            title_key = self._market_signal_key(source, title) if title else None
            summary_key = self._market_signal_key(source, summary) if summary else None
            if signal_id not in existing_ids and (
                (title_key and title_key in title_keys)
                or (summary_key and summary_key in summary_keys)
            ):
                continue
            result.append(signal)
            if signal_id:
                existing_ids.add(signal_id)
            if title_key:
                title_keys.add(title_key)
            if summary_key:
                summary_keys.add(summary_key)
        return result

    @staticmethod
    def _status_value(status: TopicIdeaStatus | str) -> str:
        return status.value if isinstance(status, TopicIdeaStatus) else str(status).strip()

    @staticmethod
    def _dump_json(value: Any, fallback: Any) -> str:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)

    @staticmethod
    def _load_json(value: Any) -> list[str]:
        if not value:
            return []
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

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
    def _market_signal_key(source: Any, value: Any) -> tuple[str, str]:
        return (str(source or "").strip(), str(value or "").strip())

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

    def _params(self, idea: TopicIdea) -> tuple[Any, ...]:
        return (
            idea.id,
            idea.status.value,
            idea.title,
            idea.genre,
            idea.world_preset,
            idea.length_tier,
            idea.logline,
            idea.premise,
            idea.protagonist_hook,
            idea.core_conflict,
            idea.opening_hook,
            self._dump_json(idea.selling_points, []),
            idea.long_term_potential,
            self._dump_json(idea.risk_notes, []),
            self._dump_json(idea.market_tags, []),
            idea.score,
            idea.adopted_novel_id,
            self._dump_json(idea.source_brief, {}),
            self._dump_json(idea.development_notes, {}),
            self._dump_json(idea.evaluation, {}),
            idea.created_at.isoformat(),
            idea.updated_at.isoformat(),
        )

    def _row_to_idea(self, row: dict[str, Any]) -> TopicIdea:
        return TopicIdea(
            id=row["id"],
            status=row.get("status") or TopicIdeaStatus.DRAFT,
            title=row["title"],
            genre=row.get("genre") or "",
            world_preset=row.get("world_preset") or "",
            length_tier=row.get("length_tier") or "",
            logline=row.get("logline") or "",
            premise=row.get("premise") or "",
            protagonist_hook=row.get("protagonist_hook") or "",
            core_conflict=row.get("core_conflict") or "",
            opening_hook=row.get("opening_hook") or "",
            selling_points=self._load_json(row.get("selling_points_json")),
            long_term_potential=row.get("long_term_potential") or "",
            risk_notes=self._load_json(row.get("risk_notes_json")),
            market_tags=self._load_json(row.get("market_tags_json")),
            score=row.get("score") or 0,
            adopted_novel_id=row.get("adopted_novel_id"),
            source_brief=self._load_json_dict(row.get("source_brief_json")),
            development_notes=self._load_json_dict(row.get("development_notes_json")),
            evaluation=self._load_json_dict(row.get("evaluation_json")),
            created_at=self._parse_dt(row.get("created_at")),
            updated_at=self._parse_dt(row.get("updated_at")),
        )

    def _row_to_market_signal(self, row: dict[str, Any]) -> TopicMarketSignalDTO:
        return TopicMarketSignalDTO(
            id=row["id"],
            source=row.get("source") or "手动观察",
            title=row.get("title") or "",
            genre=row.get("genre") or "",
            tags=self._load_json(row.get("tags_json")),
            summary=row.get("summary") or "",
            raw_text=row.get("raw_text") or "",
            created_at=str(row.get("created_at") or ""),
        )

    def _row_to_market_signal_settings(
        self,
        row: dict[str, Any],
    ) -> TopicMarketSignalAutomationSettingsDTO:
        return TopicMarketSignalAutomationSettingsDTO(
            enabled=bool(row.get("enabled")),
            interval_minutes=max(15, int(row.get("interval_minutes") or 180)),
            limit_per_source=max(1, int(row.get("limit_per_source") or 8)),
            lookback_days=max(1, int(row.get("lookback_days") or 30)),
            source_weights=self._normalize_source_weights(
                self._load_json_dict(row.get("source_weights_json"))
            ),
            selected_source_keys=self._normalize_source_keys(
                self._load_json(row.get("selected_source_keys_json"))
            ),
            last_run_at=str(row.get("last_run_at") or ""),
            last_status=str(row.get("last_status") or "idle"),
            last_error=str(row.get("last_error") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    def _row_to_market_signal_credentials(
        self,
        row: dict[str, Any],
    ) -> TopicMarketSignalSourceCredentialDTO:
        return TopicMarketSignalSourceCredentialDTO(
            source_key=str(row.get("source_key") or ""),
            api_key=str(row.get("api_key") or ""),
            cookie=str(row.get("cookie") or ""),
            endpoint_url=str(row.get("endpoint_url") or ""),
            headers=self._normalize_headers(self._load_json_dict(row.get("headers_json"))),
            updated_at=str(row.get("updated_at") or ""),
        )

    def _row_to_market_signal_source_health(
        self,
        row: dict[str, Any],
    ) -> TopicMarketSignalSourceHealthDTO:
        return TopicMarketSignalSourceHealthDTO(
            source_key=str(row.get("source_key") or ""),
            source_name="",
            status=str(row.get("status") or "unknown"),
            last_run_at=str(row.get("last_run_at") or ""),
            last_success_at=str(row.get("last_success_at") or ""),
            last_count=max(0, int(row.get("last_count") or 0)),
            last_error=str(row.get("last_error") or ""),
        )

    @staticmethod
    def _normalize_source_keys(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values or []:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _normalize_source_weights(values: dict[str, Any]) -> dict[str, float]:
        result: dict[str, float] = {}
        for key, value in (values or {}).items():
            text = str(key or "").strip()
            if not text:
                continue
            try:
                weight = float(value)
            except (TypeError, ValueError):
                continue
            result[text] = max(0.1, min(weight, 3.0))
        return result

    @staticmethod
    def _normalize_headers(values: dict[str, Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in (values or {}).items():
            name = str(key or "").strip()
            text = str(value or "").strip()
            if name and text:
                result[name] = text
        return result
