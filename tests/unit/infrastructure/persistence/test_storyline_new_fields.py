import sqlite3
from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository
from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_role import StorylineRole
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_type import StorylineType


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE storylines (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            storyline_type TEXT NOT NULL,
            status TEXT NOT NULL,
            estimated_chapter_start INTEGER NOT NULL,
            estimated_chapter_end INTEGER NOT NULL,
            current_milestone_index INTEGER DEFAULT 0,
            name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            last_active_chapter INTEGER DEFAULT 0,
            progress_summary TEXT DEFAULT '',
            extensions TEXT DEFAULT '{}',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE storyline_milestones (
            id TEXT PRIMARY KEY,
            storyline_id TEXT,
            milestone_order INTEGER,
            title TEXT,
            description TEXT,
            target_chapter_start INTEGER,
            target_chapter_end INTEGER,
            prerequisite_list TEXT,
            milestone_triggers TEXT
        )
    """)
    conn.commit()

    class _DB:
        def get_connection(self): return conn
        def fetch_one(self, sql, params=()):
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
        def fetch_all(self, sql, params=()):
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    return _DB()


def test_save_and_load_with_new_fields():
    db = _make_db()
    repo = SqliteStorylineRepository(db)

    sl = Storyline(
        id="sl-test-1",
        novel_id=NovelId("novel-test"),
        storyline_type=StorylineType.MAIN_PLOT,
        status=StorylineStatus.ACTIVE,
        estimated_chapter_start=1,
        estimated_chapter_end=80,
        role=StorylineRole.SUB,
        parent_id="sl-main-1",
        chapter_weight=0.6,
    )
    repo.save(sl)

    loaded = repo.get_by_id("sl-test-1")
    assert loaded is not None
    assert loaded.role == StorylineRole.SUB
    assert loaded.parent_id == "sl-main-1"
    assert abs(loaded.chapter_weight - 0.6) < 0.001


def test_old_data_without_role_column_defaults_to_main():
    """Simulate loading from a DB that doesn't have role/parent_id/chapter_weight columns yet."""
    db = _make_db()
    repo = SqliteStorylineRepository(db)
    # Insert directly without new columns (simulating old data)
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO storylines (id, novel_id, storyline_type, status, "
        "estimated_chapter_start, estimated_chapter_end, current_milestone_index, "
        "extensions, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("sl-old", "novel-1", "main_plot", "active", 1, 10, 0, "{}", "2024-01-01", "2024-01-01")
    )
    conn.commit()
    # Now add missing columns (repo.save would do this, but we test _row_to_storyline directly)
    # First trigger the pragma check by calling get_by_id which goes through _row_to_storyline
    loaded = repo.get_by_id("sl-old")
    assert loaded is not None
    assert loaded.role == StorylineRole.MAIN  # default
