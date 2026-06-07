import sqlite3

from infrastructure.persistence.database.migration_runner import apply_migration_files


def test_apply_migration_files_is_idempotent(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_create_sample.sql").write_text(
        "CREATE TABLE sample (id TEXT PRIMARY KEY);\n",
        encoding="utf-8",
    )

    conn = sqlite3.connect(":memory:")
    try:
        apply_migration_files(conn, migrations)
        apply_migration_files(conn, migrations)

        rows = conn.execute("SELECT migration_file FROM migrations_applied").fetchall()
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sample'"
        ).fetchone()
    finally:
        conn.close()

    assert rows == [("001_create_sample.sql",)]
    assert table == ("sample",)


def test_apply_migration_files_accepts_missing_directory(tmp_path):
    conn = sqlite3.connect(":memory:")
    try:
        apply_migration_files(conn, tmp_path / "missing")
    finally:
        conn.close()
