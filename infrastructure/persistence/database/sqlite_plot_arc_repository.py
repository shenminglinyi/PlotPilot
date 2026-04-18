"""SQLite 情节弧仓储（一书多弧以 slug 区分；读�?API 默认 slug=default）�?""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.novel.entities.plot_arc import PlotArc
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
from domain.novel.value_objects.tension_level import TensionLevel
from infrastructure.persistence.database.connection import DatabaseConnection

DEFAULT_SLUG = "default"


class SqlitePlotArcRepository(PlotArcRepository):
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def _conn(self):
        return self.db.get_connection()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def save(self, plot_arc: PlotArc) -> None:
        now = self._now()
        slug = plot_arc.slug or DEFAULT_SLUG
        conn = self._conn()
        try:
            conn.execute(
                "DELETE FROM plot_arcs WHERE novel_id = ? AND slug = ?",
                (plot_arc.novel_id.value, slug),
            )
            conn.execute(
                """
                INSERT INTO plot_arcs (
                    id, novel_id, slug, display_name, extensions, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    plot_arc.id,
                    plot_arc.novel_id.value,
                    slug,
                    plot_arc.display_name or "",
                    now,
                    now,
                ),
            )
            for i, point in enumerate(sorted(plot_arc.key_points, key=lambda p: p.chapter_number)):
                pid = f"{plot_arc.id}-p-{point.chapter_number}"
                conn.execute(
                    """
                    INSERT INTO plot_points
                    (id, plot_arc_id, sort_order, chapter_number, point_type, description, tension)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        plot_arc.id,
                        i,
                        point.chapter_number,
                        point.point_type.value,
                        point.description,
                        point.tension.value,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_by_novel_id(self, novel_id: NovelId) -> Optional[PlotArc]:
        row = self.db.fetch_one(
            """
            SELECT * FROM plot_arcs
            WHERE novel_id = ? AND slug = ?
            """,
            (novel_id.value, DEFAULT_SLUG),
        )
        if not row:
            return None
        return self._row_to_plot_arc(row, novel_id)

    def _row_to_plot_arc(self, row: dict, novel_id: NovelId) -> PlotArc:
        arc_id = row["id"]
        points = self.db.fetch_all(
            """
            SELECT chapter_number, point_type, description, tension
            FROM plot_points
            WHERE plot_arc_id = ?
            ORDER BY sort_order, chapter_number
            """,
            (arc_id,),
        )
        key_points = [
            PlotPoint(
                chapter_number=p["chapter_number"],
                point_type=PlotPointType(p["point_type"]),
                description=p["description"],
                tension=TensionLevel(int(p["tension"])),
            )
            for p in points
        ]
        slug = row.get("slug") or DEFAULT_SLUG
        display_name = row.get("display_name") or ""
        return PlotArc(
            id=arc_id,
            novel_id=novel_id,
            key_points=key_points,
            slug=slug,
            display_name=display_name,
        )

    def delete(self, novel_id: NovelId) -> None:
        row = self.db.fetch_one(
            """
            SELECT id FROM plot_arcs
            WHERE novel_id = ? AND slug = ?
            """,
            (novel_id.value, DEFAULT_SLUG),
        )
        if not row:
            return
        conn = self._conn()
        try:
            conn.execute("DELETE FROM plot_points WHERE plot_arc_id = ?", (row["id"],))
            conn.execute("DELETE FROM plot_arcs WHERE id = ?", (row["id"],))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
