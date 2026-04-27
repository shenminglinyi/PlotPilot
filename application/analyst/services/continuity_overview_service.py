"""连续性总览服务

为作者工作台提供轻量的连续性提醒聚合：
- 角色掉线提醒
- 时间线覆盖情况
- 文风漂移告警
- 关系聚焦摘要
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from domain.novel.value_objects.novel_id import NovelId


@dataclass
class _CharacterAppearanceStat:
    character_id: str
    last_appearance_chapter: int
    appearance_count: int


class ContinuityOverviewService:
    """聚合现有 v1.0.4 数据源的连续性提醒。"""

    def __init__(
        self,
        *,
        bible_service,
        chapter_service,
        voice_drift_service,
        timeline_repository,
        db_connection,
    ) -> None:
        self.bible_service = bible_service
        self.chapter_service = chapter_service
        self.voice_drift_service = voice_drift_service
        self.timeline_repository = timeline_repository
        self.db_connection = db_connection

    def get_overview(
        self,
        novel_id: str,
        chapter_number: Optional[int] = None,
        *,
        dropout_gap: int = 5,
        max_dropouts: int = 6,
        max_timeline_events: int = 5,
        max_relationships: int = 6,
    ) -> dict[str, Any]:
        chapters = self.chapter_service.list_chapters_by_novel(novel_id)
        latest_chapter_number = max((chapter.number for chapter in chapters), default=0)
        current_chapter_number = chapter_number or latest_chapter_number

        bible = self.bible_service.get_bible_by_novel(novel_id)
        drift_report = self.voice_drift_service.get_drift_report(novel_id)
        timeline_registry = self.timeline_repository.get_by_novel_id(NovelId(novel_id))

        appearance_stats = self._load_character_appearance_stats(novel_id, current_chapter_number)
        dropouts = self._build_character_dropouts(
            bible=bible,
            current_chapter_number=current_chapter_number,
            appearance_stats=appearance_stats,
            dropout_gap=dropout_gap,
            max_dropouts=max_dropouts,
        )
        timeline = self._build_timeline_summary(
            timeline_registry=timeline_registry,
            current_chapter_number=current_chapter_number,
            max_timeline_events=max_timeline_events,
        )
        relationships = self._build_relationship_spotlights(
            bible=bible,
            max_relationships=max_relationships,
        )

        scores = list(drift_report.get("scores", []) or [])
        latest_score = scores[-1] if scores else None

        return {
            "novel_id": novel_id,
            "chapter_number": current_chapter_number,
            "latest_chapter_number": latest_chapter_number,
            "character_dropouts": dropouts,
            "relationship_spotlights": relationships,
            "voice_drift": {
                "drift_alert": bool(drift_report.get("drift_alert", False)),
                "latest_similarity_score": latest_score.get("similarity_score") if latest_score else None,
                "scored_chapters": len(scores),
                "alert_threshold": drift_report.get("alert_threshold", 0.75),
                "alert_consecutive": drift_report.get("alert_consecutive", 5),
            },
            "timeline": timeline,
        }

    def _load_character_appearance_stats(
        self,
        novel_id: str,
        current_chapter_number: int,
    ) -> dict[str, _CharacterAppearanceStat]:
        if current_chapter_number <= 0:
            return {}

        cursor = self.db_connection.execute(
            """
            SELECT
                ce.element_id AS character_id,
                MAX(sn.number) AS last_appearance_chapter,
                COUNT(DISTINCT sn.number) AS appearance_count
            FROM chapter_elements ce
            JOIN story_nodes sn
              ON sn.id = ce.chapter_id
             AND sn.novel_id = ?
             AND sn.node_type = 'chapter'
            WHERE ce.element_type = 'character'
              AND ce.relation_type = 'appears'
              AND sn.number <= ?
            GROUP BY ce.element_id
            """,
            (novel_id, current_chapter_number),
        )

        stats: dict[str, _CharacterAppearanceStat] = {}
        for row in cursor.fetchall():
            stats[row["character_id"]] = _CharacterAppearanceStat(
                character_id=row["character_id"],
                last_appearance_chapter=int(row["last_appearance_chapter"] or 0),
                appearance_count=int(row["appearance_count"] or 0),
            )
        return stats

    def _build_character_dropouts(
        self,
        *,
        bible,
        current_chapter_number: int,
        appearance_stats: dict[str, _CharacterAppearanceStat],
        dropout_gap: int,
        max_dropouts: int,
    ) -> list[dict[str, Any]]:
        if not bible or current_chapter_number <= 0:
            return []

        dropouts: list[dict[str, Any]] = []
        for character in bible.characters:
            stat = appearance_stats.get(character.id)
            if stat is None or stat.last_appearance_chapter <= 0:
                continue

            chapters_absent = current_chapter_number - stat.last_appearance_chapter
            if chapters_absent < dropout_gap:
                continue

            severity = "high" if chapters_absent >= 10 else "medium" if chapters_absent >= 7 else "low"
            dropouts.append(
                {
                    "character_id": character.id,
                    "character_name": character.name,
                    "last_appearance_chapter": stat.last_appearance_chapter,
                    "chapters_absent": chapters_absent,
                    "appearance_count": stat.appearance_count,
                    "severity": severity,
                }
            )

        dropouts.sort(
            key=lambda item: (
                -item["chapters_absent"],
                -item["appearance_count"],
                item["character_name"],
            )
        )
        return dropouts[:max_dropouts]

    def _build_timeline_summary(
        self,
        *,
        timeline_registry,
        current_chapter_number: int,
        max_timeline_events: int,
    ) -> dict[str, Any]:
        if timeline_registry is None:
            return {
                "total_events": 0,
                "current_chapter_has_event": False,
                "current_chapter_events": [],
                "recent_events": [],
            }

        events = list(timeline_registry.get_all_events_sorted())
        current_events = [event for event in events if event.chapter_number == current_chapter_number]
        recent_events = [event for event in events if event.chapter_number <= current_chapter_number][-max_timeline_events:]

        def _serialize(event) -> dict[str, Any]:
            return {
                "id": event.id,
                "chapter_number": event.chapter_number,
                "event": event.event,
                "timestamp": event.timestamp,
                "timestamp_type": event.timestamp_type,
            }

        return {
            "total_events": len(events),
            "current_chapter_has_event": len(current_events) > 0,
            "current_chapter_events": [_serialize(event) for event in current_events],
            "recent_events": [_serialize(event) for event in recent_events],
        }

    def _build_relationship_spotlights(
        self,
        *,
        bible,
        max_relationships: int,
    ) -> list[dict[str, Any]]:
        if not bible:
            return []

        items: list[dict[str, Any]] = []
        for character in bible.characters:
            relationships = list(getattr(character, "relationships", []) or [])
            for relationship in relationships:
                if isinstance(relationship, dict):
                    target_name = (
                        relationship.get("target")
                        or relationship.get("target_name")
                        or relationship.get("character")
                        or ""
                    )
                    relation = (
                        relationship.get("relation")
                        or relationship.get("type")
                        or relationship.get("label")
                        or relationship.get("status")
                        or "关系"
                    )
                    description = relationship.get("description") or ""
                else:
                    target_name = ""
                    relation = str(relationship)
                    description = ""

                if not relation.strip():
                    continue

                items.append(
                    {
                        "source_character": character.name,
                        "target_character": target_name,
                        "relation": relation,
                        "description": description,
                    }
                )

                if len(items) >= max_relationships:
                    return items
        return items
