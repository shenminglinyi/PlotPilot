"""SQLite SQL migration runner."""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def apply_migration_files(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    """Apply SQL migrations idempotently using the existing tracking table."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS migrations_applied (
                    migration_file TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            break
        except sqlite3.OperationalError as exc:
            if "database is locked" in str(exc) and attempt < max_retries - 1:
                logger.warning(
                    "Database locked, retrying... (attempt %s/%s)",
                    attempt + 1,
                    max_retries,
                )
                time.sleep(0.5 * (attempt + 1))
                continue
            if "already exists" in str(exc):
                break
            logger.warning(
                "Cannot create migrations_applied table: %s, using legacy mode",
                exc,
            )
            apply_migration_files_legacy(conn, migrations_dir)
            return

    applied = set()
    try:
        cursor = conn.execute("SELECT migration_file FROM migrations_applied")
        applied = {row[0] for row in cursor.fetchall()}
    except Exception:
        pass

    if not migrations_dir.is_dir():
        logger.warning(
            "未找到迁移目录（将仅依赖 schema.sql 与代码内补丁）: %s",
            migrations_dir,
        )
        return

    new_migrations = 0
    for migration_path in sorted(migrations_dir.glob("*.sql")):
        migration_file = migration_path.name
        if migration_file in applied:
            continue

        try:
            migration_sql = migration_path.read_text(encoding="utf-8")
            conn.executescript(migration_sql)
            conn.execute(
                "INSERT OR IGNORE INTO migrations_applied (migration_file) VALUES (?)",
                (migration_file,),
            )
            conn.commit()
            logger.info("Applied migration: %s", migration_file)
            new_migrations += 1
        except sqlite3.OperationalError as exc:
            err = str(exc)
            if "already exists" in err or "duplicate column" in err:
                _mark_applied(conn, migration_file)
                logger.debug("Migration %s already applied: %s", migration_file, exc)
            elif "no such function" in err:
                _mark_applied(conn, migration_file)
                logger.warning(
                    "Migration %s uses unsupported SQLite function, marking as applied: %s",
                    migration_file,
                    exc,
                )
            else:
                logger.warning("Migration %s failed: %s", migration_file, exc)
        except Exception as exc:
            logger.warning("Failed to apply migration %s: %s", migration_file, exc)

    if new_migrations == 0 and applied:
        logger.debug("All %d migrations already applied, skipped", len(applied))


def apply_migration_files_legacy(
    conn: sqlite3.Connection, migrations_dir: Path
) -> None:
    """Legacy migration mode without a tracking table."""
    if not migrations_dir.is_dir():
        logger.warning(
            "未找到迁移目录（将仅依赖 schema.sql 与代码内补丁）: %s",
            migrations_dir,
        )
        return

    for migration_path in sorted(migrations_dir.glob("*.sql")):
        migration_file = migration_path.name
        try:
            migration_sql = migration_path.read_text(encoding="utf-8")
            conn.executescript(migration_sql)
            conn.commit()
            logger.info("Applied migration: %s", migration_file)
        except sqlite3.OperationalError as exc:
            if "already exists" in str(exc) or "duplicate column" in str(exc):
                logger.debug("Migration %s already applied: %s", migration_file, exc)
            else:
                logger.warning("Migration %s failed: %s", migration_file, exc)
        except OSError as exc:
            logger.warning("Failed to read migration %s: %s", migration_file, exc)
        except Exception as exc:
            logger.warning("Failed to apply migration %s: %s", migration_file, exc)


def _mark_applied(conn: sqlite3.Connection, migration_file: str) -> None:
    try:
        conn.execute(
            "INSERT OR IGNORE INTO migrations_applied (migration_file) VALUES (?)",
            (migration_file,),
        )
        conn.commit()
    except Exception:
        pass
