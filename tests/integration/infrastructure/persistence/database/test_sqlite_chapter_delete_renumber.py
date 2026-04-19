"""删除章节后事务内重排 chapter_number 并级联相关表。"""

from pathlib import Path

import pytest

from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_chapter_repository import (
    SqliteChapterRepository,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[5]
    / "infrastructure"
    / "persistence"
    / "database"
    / "schema.sql"
)


@pytest.fixture
def db():
    database = DatabaseConnection(":memory:")
    database.get_connection().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    database.get_connection().execute("PRAGMA foreign_keys = ON")
    database.get_connection().commit()
    yield database
    database.close()


@pytest.fixture
def repo(db):
    return SqliteChapterRepository(db)


def _seed_three_chapters(db, novel_id: str = "novel-del-1"):
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        (novel_id, "N", "slug-del-1", 10),
    )
    db.execute(
        "INSERT INTO knowledge (id, novel_id, version) VALUES (?, ?, ?)",
        (f"k-{novel_id}", novel_id, 1),
    )
    db.execute(
        """
        INSERT INTO storylines (
            id, novel_id, storyline_type, status,
            estimated_chapter_start, estimated_chapter_end,
            current_milestone_index, extensions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"sl-{novel_id}",
            novel_id,
            "main",
            "active",
            1,
            3,
            0,
            "{}",
        ),
    )
    for num, cid in [(1, "c1"), (2, "c2"), (3, "c3")]:
        db.execute(
            """
            INSERT INTO chapters (id, novel_id, number, title, content, outline, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cid, novel_id, num, f"T{num}", f"body{num}", "", "draft"),
        )
    db.execute(
        """
        INSERT INTO chapter_reviews (novel_id, chapter_number, status, memo)
        VALUES (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)
        """,
        (
            novel_id,
            1,
            "draft",
            "",
            novel_id,
            2,
            "draft",
            "",
            novel_id,
            3,
            "draft",
            "",
        ),
    )
    db.execute(
        """
        INSERT INTO triples (
            id, novel_id, subject, predicate, object, chapter_number, first_appearance
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("tr-1", novel_id, "a", "b", "c", 3, 3),
    )
    db.execute(
        """
        INSERT INTO plot_arcs (id, novel_id, slug, display_name, extensions)
        VALUES (?, ?, ?, ?, ?)
        """,
        (f"pa-{novel_id}", novel_id, "default", "A", "{}"),
    )
    db.execute(
        """
        INSERT INTO plot_points (
            id, plot_arc_id, sort_order, chapter_number, point_type, description, tension
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (f"pa-{novel_id}-p-3", f"pa-{novel_id}", 0, 3, "beat", "x", 50),
    )
    db.get_connection().commit()


def test_delete_middle_chapter_renumbers_and_cascades(db, repo):
    novel_id = "novel-del-1"
    _seed_three_chapters(db, novel_id)

    repo.delete(ChapterId("c2"))

    rows = db.fetch_all(
        "SELECT id, number FROM chapters WHERE novel_id = ? ORDER BY number",
        (novel_id,),
    )
    assert [r["number"] for r in rows] == [1, 2]
    assert {r["id"] for r in rows} == {"c1", "c3"}

    tr = db.fetch_one(
        "SELECT chapter_number, first_appearance FROM triples WHERE id = ?",
        ("tr-1",),
    )
    assert tr["chapter_number"] == 2
    assert tr["first_appearance"] == 2

    pp = db.fetch_one(
        "SELECT id, chapter_number FROM plot_points WHERE plot_arc_id = ?",
        (f"pa-{novel_id}",),
    )
    assert pp["chapter_number"] == 2
    assert pp["id"] == f"pa-{novel_id}-p-2"

    rev = db.fetch_all(
        "SELECT chapter_number FROM chapter_reviews WHERE novel_id = ? ORDER BY chapter_number",
        (novel_id,),
    )
    assert [r["chapter_number"] for r in rev] == [1, 2]

    sl = db.fetch_one(
        "SELECT estimated_chapter_end FROM storylines WHERE novel_id = ?",
        (novel_id,),
    )
    assert sl["estimated_chapter_end"] == 2


def test_delete_last_chapter_no_shift_still_adjusts_bounds(db, repo):
    novel_id = "novel-del-2"
    _seed_three_chapters(db, novel_id)

    repo.delete(ChapterId("c3"))

    rows = db.fetch_all(
        "SELECT number FROM chapters WHERE novel_id = ? ORDER BY number",
        (novel_id,),
    )
    assert [r["number"] for r in rows] == [1, 2]

    sl = db.fetch_one(
        "SELECT estimated_chapter_end FROM storylines WHERE novel_id = ?",
        (novel_id,),
    )
    assert sl["estimated_chapter_end"] == 2
