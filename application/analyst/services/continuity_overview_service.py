"""连续性总览服务

为作者工作台提供轻量的连续性提醒聚合：
- 角色掉线提醒
- 时间线覆盖情况
- 文风漂移告警
- 关系聚焦摘要
- 关系变化追踪
- 大纲与正文偏离提醒
"""
from __future__ import annotations

from dataclasses import dataclass
import re
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
        chapter_context = self._load_current_chapter_context(novel_id, current_chapter_number)
        relationship_tracking = self._build_relationship_tracking(
            novel_id=novel_id,
            bible=bible,
            current_chapter_number=current_chapter_number,
            max_relationships=max_relationships,
            chapter_context=chapter_context,
        )
        dropouts = self._attach_dropout_relationship_context(
            dropouts=dropouts,
            bible=bible,
            relationship_tracking=relationship_tracking,
        )
        outline_deviation = self._build_outline_deviation(
            chapter_context=chapter_context,
        )

        scores = list(drift_report.get("scores", []) or [])
        latest_score = scores[-1] if scores else None

        return {
            "novel_id": novel_id,
            "chapter_number": current_chapter_number,
            "latest_chapter_number": latest_chapter_number,
            "character_dropouts": dropouts,
            "relationship_spotlights": relationships,
            "relationship_tracking": relationship_tracking,
            "voice_drift": {
                "drift_alert": bool(drift_report.get("drift_alert", False)),
                "latest_similarity_score": latest_score.get("similarity_score") if latest_score else None,
                "scored_chapters": len(scores),
                "alert_threshold": drift_report.get("alert_threshold", 0.75),
                "alert_consecutive": drift_report.get("alert_consecutive", 5),
            },
            "timeline": timeline,
            "outline_deviation": outline_deviation,
        }

    def _get_table_columns(self, table_name: str) -> set[str]:
        try:
            rows = self.db_connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        except Exception:
            return set()
        return {str(row["name"]) for row in rows if row["name"]}

    def _load_current_chapter_context(self, novel_id: str, chapter_number: int) -> dict[str, str]:
        context = {
            "content": "",
            "outline": "",
            "summary": "",
            "key_events": "",
            "open_threads": "",
            "consistency_note": "",
            "review_memo": "",
        }
        if chapter_number <= 0:
            return context

        chapter_row = self.db_connection.execute(
            """
            SELECT
                ch.content AS chapter_content,
                ch.outline AS chapter_outline,
                sn.outline AS story_outline
            FROM chapters ch
            LEFT JOIN story_nodes sn
              ON sn.novel_id = ch.novel_id
             AND sn.node_type = 'chapter'
             AND sn.number = ch.number
            WHERE ch.novel_id = ?
              AND ch.number = ?
            LIMIT 1
            """,
            (novel_id, chapter_number),
        ).fetchone()
        if chapter_row:
            context["content"] = str(chapter_row["chapter_content"] or "")
            context["outline"] = str(chapter_row["story_outline"] or chapter_row["chapter_outline"] or "")

        summary_columns = self._get_table_columns("chapter_summaries")
        if summary_columns:
            select_columns = ["cs.summary"]
            optional_columns = []
            for column in ("key_events", "open_threads", "consistency_note"):
                if column in summary_columns:
                    select_columns.append(f"cs.{column}")
                    optional_columns.append(column)

            summary_row = self.db_connection.execute(
                f"""
                SELECT {", ".join(select_columns)}
                FROM chapter_summaries cs
                JOIN knowledge k ON k.id = cs.knowledge_id
                WHERE k.novel_id = ?
                  AND cs.chapter_number = ?
                LIMIT 1
                """,
                (novel_id, chapter_number),
            ).fetchone()
            if summary_row:
                context["summary"] = str(summary_row["summary"] or "")
                for column in optional_columns:
                    context[column] = str(summary_row[column] or "")

        review_columns = self._get_table_columns("chapter_reviews")
        if "memo" in review_columns:
            review_row = self.db_connection.execute(
                """
                SELECT memo
                FROM chapter_reviews
                WHERE novel_id = ?
                  AND chapter_number = ?
                LIMIT 1
                """,
                (novel_id, chapter_number),
            ).fetchone()
            if review_row:
                context["review_memo"] = str(review_row["memo"] or "")

        return context

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

    def _build_relationship_tracking(
        self,
        *,
        novel_id: str,
        bible,
        current_chapter_number: int,
        max_relationships: int,
        chapter_context: dict[str, str],
    ) -> dict[str, Any]:
        if not bible or current_chapter_number <= 0:
            return {
                "tracked_pairs": 0,
                "active_signals": [],
                "stale_pairs": [],
            }

        name_to_id = {
            str(character.name or ""): str(character.id or "")
            for character in bible.characters
            if getattr(character, "name", None) and getattr(character, "id", None)
        }
        active_signals: list[dict[str, Any]] = []
        stale_pairs: list[dict[str, Any]] = []
        tracked_pairs = 0
        text_bundle = "\n".join(
            [
                chapter_context.get("summary", ""),
                chapter_context.get("key_events", ""),
                chapter_context.get("open_threads", ""),
                chapter_context.get("consistency_note", ""),
                chapter_context.get("review_memo", ""),
                chapter_context.get("content", "")[:600],
            ]
        )

        for character in bible.characters:
            source_name = str(getattr(character, "name", "") or "").strip()
            source_id = str(getattr(character, "id", "") or "").strip()
            relationships = list(getattr(character, "relationships", []) or [])

            for relationship in relationships:
                if not source_name or not source_id:
                    continue
                target_name = ""
                relation = "关系"
                description = ""
                if isinstance(relationship, dict):
                    target_name = str(
                        relationship.get("target")
                        or relationship.get("target_name")
                        or relationship.get("character")
                        or ""
                    ).strip()
                    relation = str(
                        relationship.get("relation")
                        or relationship.get("type")
                        or relationship.get("label")
                        or relationship.get("status")
                        or "关系"
                    ).strip() or "关系"
                    description = str(relationship.get("description") or "").strip()
                else:
                    relation = str(relationship).strip() or "关系"

                tracked_pairs += 1
                target_id = name_to_id.get(target_name, "")
                joint_stat = self._load_joint_appearance_stat(
                    novel_id=novel_id,
                    current_chapter_number=current_chapter_number,
                    source_id=source_id,
                    target_id=target_id,
                ) if target_id else None

                last_joint_chapter = int((joint_stat or {}).get("last_joint_chapter") or 0)
                joint_appearance_count = int((joint_stat or {}).get("joint_appearance_count") or 0)
                chapters_since_joint = (
                    current_chapter_number - last_joint_chapter if last_joint_chapter > 0 else None
                )
                change_signal, severity = self._infer_relationship_signal(
                    text_bundle=text_bundle,
                    source_name=source_name,
                    target_name=target_name,
                )
                signal_excerpt = self._extract_signal_excerpt(text_bundle, source_name, target_name)

                if last_joint_chapter == current_chapter_number or change_signal:
                    active_signals.append(
                        {
                            "source_character": source_name,
                            "target_character": target_name,
                            "relation": relation,
                            "description": description,
                            "last_joint_chapter": last_joint_chapter,
                            "joint_appearance_count": joint_appearance_count,
                            "change_signal": change_signal or "本章有关系推进",
                            "signal_excerpt": signal_excerpt,
                            "severity": severity or "info",
                        }
                    )
                elif chapters_since_joint is not None and chapters_since_joint >= 5:
                    stale_pairs.append(
                        {
                            "source_character": source_name,
                            "target_character": target_name,
                            "relation": relation,
                            "description": description,
                            "last_joint_chapter": last_joint_chapter,
                            "chapters_since_joint": chapters_since_joint,
                            "severity": "warning" if chapters_since_joint >= 8 else "info",
                        }
                    )

        active_signals.sort(
            key=lambda item: (
                item["severity"] != "warning",
                -(item["last_joint_chapter"] or 0),
                item["source_character"],
            )
        )
        stale_pairs.sort(
            key=lambda item: (
                -item["chapters_since_joint"],
                item["source_character"],
            )
        )
        return {
            "tracked_pairs": tracked_pairs,
            "active_signals": active_signals[:max_relationships],
            "stale_pairs": stale_pairs[:max_relationships],
        }

    def _attach_dropout_relationship_context(
        self,
        *,
        dropouts: list[dict[str, Any]],
        bible,
        relationship_tracking: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not dropouts:
            return dropouts

        tracked_map = self._build_character_relationship_map(bible)
        stale_map: dict[str, list[str]] = {}

        for item in relationship_tracking.get("stale_pairs", []) or []:
            source_name = str(item.get("source_character") or "").strip()
            target_name = str(item.get("target_character") or "").strip()
            if source_name and target_name:
                stale_map.setdefault(source_name, []).append(target_name)
                stale_map.setdefault(target_name, []).append(source_name)

        enriched: list[dict[str, Any]] = []
        for item in dropouts:
            name = str(item.get("character_name") or "").strip()
            tracked_targets = list(dict.fromkeys(tracked_map.get(name, [])))
            stale_targets = list(dict.fromkeys(stale_map.get(name, [])))

            if stale_targets:
                dropout_scope = "linked"
            elif tracked_targets:
                dropout_scope = "tracked"
            else:
                dropout_scope = "solo"

            enriched.append(
                {
                    **item,
                    "tracked_relationship_count": len(tracked_targets),
                    "stale_relationship_count": len(stale_targets),
                    "stale_relationship_targets": stale_targets,
                    "dropout_scope": dropout_scope,
                }
            )
        return enriched

    def _build_character_relationship_map(self, bible) -> dict[str, list[str]]:
        if not bible:
            return {}

        relationship_map: dict[str, list[str]] = {}
        for character in bible.characters:
            source_name = str(getattr(character, "name", "") or "").strip()
            if not source_name:
                continue

            for relationship in list(getattr(character, "relationships", []) or []):
                if isinstance(relationship, dict):
                    target_name = str(
                        relationship.get("target")
                        or relationship.get("target_name")
                        or relationship.get("character")
                        or ""
                    ).strip()
                else:
                    target_name = ""

                if not target_name:
                    continue
                relationship_map.setdefault(source_name, []).append(target_name)
                relationship_map.setdefault(target_name, []).append(source_name)
        return relationship_map

    def _load_joint_appearance_stat(
        self,
        *,
        novel_id: str,
        current_chapter_number: int,
        source_id: str,
        target_id: str,
    ) -> Optional[dict[str, int]]:
        row = self.db_connection.execute(
            """
            SELECT
                MAX(sn.number) AS last_joint_chapter,
                COUNT(DISTINCT sn.number) AS joint_appearance_count
            FROM story_nodes sn
            JOIN chapter_elements ce1
              ON ce1.chapter_id = sn.id
             AND ce1.element_type = 'character'
             AND ce1.relation_type = 'appears'
             AND ce1.element_id = ?
            JOIN chapter_elements ce2
              ON ce2.chapter_id = sn.id
             AND ce2.element_type = 'character'
             AND ce2.relation_type = 'appears'
             AND ce2.element_id = ?
            WHERE sn.novel_id = ?
              AND sn.node_type = 'chapter'
              AND sn.number <= ?
            """,
            (source_id, target_id, novel_id, current_chapter_number),
        ).fetchone()
        if not row:
            return None
        return {
            "last_joint_chapter": int(row["last_joint_chapter"] or 0),
            "joint_appearance_count": int(row["joint_appearance_count"] or 0),
        }

    def _infer_relationship_signal(
        self,
        *,
        text_bundle: str,
        source_name: str,
        target_name: str,
    ) -> tuple[str, str]:
        if not source_name or not target_name:
            return "", ""
        normalized = self._normalize_text(text_bundle)
        if source_name not in normalized or target_name not in normalized:
            return "", ""

        conflict_markers = ("裂痕", "疏远", "争执", "冲突", "敌意", "不信任", "决裂", "紧张", "对峙")
        warm_markers = ("和解", "靠近", "信任", "默契", "亲近", "依赖", "联手", "暧昧", "升温")

        if any(marker in normalized for marker in conflict_markers):
            return "关系趋紧", "warning"
        if any(marker in normalized for marker in warm_markers):
            return "关系升温", "success"
        return "本章有关系推进", "info"

    def _extract_signal_excerpt(self, text_bundle: str, source_name: str, target_name: str) -> str:
        for raw_line in re.split(r"[。！？\n]+", text_bundle):
            line = raw_line.strip()
            if not line:
                continue
            if source_name in line and target_name in line:
                return line[:80]
        return ""

    def _build_outline_deviation(self, *, chapter_context: dict[str, str]) -> dict[str, Any]:
        outline = str(chapter_context.get("outline", "") or "").strip()
        summary_text = str(chapter_context.get("summary", "") or "").strip()
        basis_text = summary_text or str(chapter_context.get("key_events", "") or "").strip()
        if not basis_text:
            basis_text = str(chapter_context.get("content", "") or "").strip()[:180]

        if not outline:
            return {
                "status": "unavailable",
                "overlap_score": None,
                "outline_excerpt": "",
                "summary_excerpt": basis_text,
                "warning_reasons": ["当前章节还没有可用大纲"],
            }
        if not basis_text:
            return {
                "status": "unavailable",
                "overlap_score": None,
                "outline_excerpt": outline[:120],
                "summary_excerpt": "",
                "warning_reasons": ["当前章节缺少可用于比对的正文摘要"],
            }

        outline_segments = self._split_outline_segments(outline)
        normalized_basis = self._normalize_text(basis_text)
        matched_segments = [
            segment
            for segment in outline_segments
            if self._normalize_text(segment) and self._normalize_text(segment) in normalized_basis
        ]
        overlap_score = (
            round(len(matched_segments) / len(outline_segments), 2)
            if outline_segments
            else 0.0
        )

        review_memo = str(chapter_context.get("review_memo", "") or "")
        warning_reasons: list[str] = []
        if self._contains_outline_drift_marker(review_memo):
            warning_reasons.append("审阅备注提示可能偏离大纲")
        if outline_segments and overlap_score < 0.34:
            warning_reasons.append("章节摘要与章节大纲重合度偏低")
        elif outline_segments and overlap_score < 0.55:
            warning_reasons.append("章节摘要只覆盖了部分大纲节点")

        if not warning_reasons:
            status = "aligned"
        elif any("偏离大纲" in reason or "重合度偏低" in reason for reason in warning_reasons):
            status = "warning"
        else:
            status = "watch"

        return {
            "status": status,
            "overlap_score": overlap_score,
            "outline_excerpt": outline[:120],
            "summary_excerpt": basis_text[:120],
            "warning_reasons": warning_reasons,
        }

    def _split_outline_segments(self, outline: str) -> list[str]:
        segments: list[str] = []
        seen: set[str] = set()
        for raw in re.split(r"[，。；：、\n]+", outline):
            segment = raw.strip()
            segment = re.sub(r"^(并且|并|随后|然后|最终|最后|接着)", "", segment)
            if len(segment) < 4:
                continue
            if segment in seen:
                continue
            seen.add(segment)
            segments.append(segment)
        return segments

    def _contains_outline_drift_marker(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False
        markers = ("偏离", "不一致", "不完全一致", "新增设定", "跳出大纲", "脱纲", "失控")
        return any(marker in normalized for marker in markers)

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", "", str(text or ""))
