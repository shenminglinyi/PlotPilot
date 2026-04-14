import sqlite3
from pathlib import Path

import pytest

from application.world.services.bible_location_triple_sync import BibleLocationTripleSyncService
from infrastructure.persistence.database.triple_repository import TripleRepository

SCHEMA_PATH = (
    Path(__file__).resolve().parents[4] / "infrastructure" / "persistence" / "database" / "schema.sql"
)


@pytest.fixture
def sync_service(tmp_path):
    db_path = tmp_path / "sync.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES ('novel-1', 'T', 'slug-sync', 0)"
    )
    conn.commit()
    conn.close()
    repo = TripleRepository(str(db_path))
    return BibleLocationTripleSyncService(repo), str(db_path)


def test_sync_idempotent(sync_service):
    svc, _ = sync_service
    locs = [
        {"id": "root", "name": "大陆", "parent_id": None},
        {"id": "city", "name": "城", "parent_id": "root"},
    ]
    svc.sync_from_locations("novel-1", locs)
    svc.sync_from_locations("novel-1", locs)
    repo = svc._repo
    rows = repo._db.fetch_all(
        "SELECT id FROM triples WHERE novel_id = ? AND predicate = '位于'",
        ("novel-1",),
    )
    assert len(rows) == 1
    anchors = repo._db.fetch_all(
        "SELECT id FROM triples WHERE novel_id = ? AND predicate = '地图地点'",
        ("novel-1",),
    )
    assert len(anchors) == 2


def test_root_removes_containment(sync_service):
    svc, _ = sync_service
    svc.sync_from_locations(
        "novel-1",
        [
            {"id": "root", "name": "R", "parent_id": None},
            {"id": "c", "name": "C", "parent_id": "root"},
        ],
    )
    svc.sync_from_locations(
        "novel-1",
        [
            {"id": "root", "name": "R", "parent_id": None},
            {"id": "c", "name": "C", "parent_id": None},
        ],
    )
    rows = svc._repo._db.fetch_all(
        "SELECT id FROM triples WHERE novel_id = ? AND predicate = '位于'",
        ("novel-1",),
    )
    assert len(rows) == 0
    anchors = svc._repo._db.fetch_all(
        "SELECT id FROM triples WHERE novel_id = ? AND predicate = '地图地点'",
        ("novel-1",),
    )
    assert len(anchors) == 2


def test_remove_location_deletes_anchor(sync_service):
    svc, _ = sync_service
    svc.sync_from_locations(
        "novel-1",
        [
            {"id": "a", "name": "A", "parent_id": None},
            {"id": "b", "name": "B", "parent_id": None},
        ],
    )
    svc.sync_from_locations(
        "novel-1",
        [{"id": "a", "name": "A", "parent_id": None}],
    )
    anchors = svc._repo._db.fetch_all(
        "SELECT id FROM triples WHERE novel_id = ? AND predicate = '地图地点'",
        ("novel-1",),
    )
    assert len(anchors) == 1


def test_chapter_inferred_untouched(sync_service):
    svc, db_path = sync_service
    repo = svc._repo
    tid = "manual-inf-1"
    repo._db.execute(
        """
        INSERT INTO triples (
            id, novel_id, subject, predicate, object, chapter_number, note,
            entity_type, importance, location_type, description, first_appearance,
            confidence, source_type, subject_entity_id, object_entity_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, NULL, '', 'location', NULL, NULL, NULL, NULL,
            1.0, 'chapter_inferred', 'x', 'y', datetime('now'), datetime('now'))
        """,
        (tid, "novel-1", "x", "位于", "y"),
    )
    repo._db.get_connection().commit()
    svc.sync_from_locations(
        "novel-1",
        [{"id": "root", "name": "R", "parent_id": None}],
    )
    row = repo._db.fetch_one("SELECT id FROM triples WHERE id = ?", (tid,))
    assert row is not None
