import sqlite3
from contextlib import closing
from pathlib import Path

from infrastructure.persistence.database.sqlite_chapter_repository import read_completed_revisions


MIGRATION = Path(__file__).resolve().parents[5] / (
    "infrastructure/persistence/database/migrations/add_chapter_manuscript_revision.sql"
)


def test_chapter_revisions_survive_restart_and_change_atomically_with_prose(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    archive = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(path)) as writer:
        writer.row_factory = sqlite3.Row
        writer.execute("""CREATE TABLE chapters(id TEXT PRIMARY KEY, novel_id TEXT, number INTEGER,
                           status TEXT, content TEXT, updated_at TEXT, title TEXT)""")
        writer.executemany("INSERT INTO chapters VALUES(?, 'book', ?, ?, ?, 'same-second','岛')", [
            ("c1", 1, "completed", "她决定留下。"),
            ("c2", 2, "completed", " \n\t　"),
            ("c3", 3, "draft", "半章"),
        ])
        writer.commit()
        with closing(sqlite3.connect(archive, uri=True)) as reader:
            reader.row_factory = sqlite3.Row
            legacy = read_completed_revisions(reader.execute, "book")
            assert set(legacy) == {1}
            writer.executescript(MIGRATION.read_text(encoding="utf-8"))
            original = read_completed_revisions(reader.execute, "book")
            assert set(original) == {1}
            assert original[1] != legacy[1]

            from types import SimpleNamespace
            from interfaces.api.v1.core.chapters import get_chapter_evidence_source

            db = SimpleNamespace(fetch_one=lambda sql, params: dict(reader.execute(sql, params).fetchone()))
            monkeypatch.setattr("infrastructure.persistence.database.connection.get_database", lambda: db)
            signed = get_chapter_evidence_source("book", 1)
            assert (signed["content"], signed["manuscript_revision"]) == ("她决定留下。", original[1])
            writer.execute("UPDATE chapters SET content = '她决定离开。' WHERE id = 'c1'")
            assert read_completed_revisions(reader.execute, "book") == original
            changed = read_completed_revisions(writer.execute, "book")
            assert changed[1] != original[1]
            writer.rollback()
            assert read_completed_revisions(writer.execute, "book") == original

            writer.execute("UPDATE chapters SET content = '她决定离开。' WHERE id = 'c1'")
            writer.commit()
            changed = read_completed_revisions(reader.execute, "book")
            assert changed != original
            source = get_chapter_evidence_source("book", 1)
            assert source["content"].startswith("她决定") and source["content"] != signed["content"]
            assert source["manuscript_revision"] == changed[1] != signed["manuscript_revision"]
            writer.execute("UPDATE chapters SET content = content, updated_at = 'later' WHERE id = 'c1'")
            writer.execute("UPDATE chapters SET status = 'completed' WHERE id = 'c3'")
            writer.execute("INSERT INTO chapters(id, novel_id, number, status, content) "
                           "VALUES('c4','book',4,'completed','新章')")
            writer.commit()

    with closing(sqlite3.connect(archive, uri=True)) as restarted:
        restarted.row_factory = sqlite3.Row
        current = read_completed_revisions(restarted.execute, "book")
        assert set(current) == {1, 3, 4}
        assert current[1] == changed[1]
        assert len(set(current.values())) == 3
