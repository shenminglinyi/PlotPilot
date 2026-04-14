"""SQLite 数据库连接管理"""
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def _migrate_triples_columns(conn: sqlite3.Connection) -> None:
    """为已存在的 triples 表补齐统一知识模型列（开发期可重复执行）。"""
    cur = conn.execute("PRAGMA table_info(triples)")
    cols = {row[1] for row in cur.fetchall()}
    if not cols:
        return
    alters = []
    if "confidence" not in cols:
        alters.append("ALTER TABLE triples ADD COLUMN confidence REAL")
    if "source_type" not in cols:
        alters.append("ALTER TABLE triples ADD COLUMN source_type TEXT")
    if "subject_entity_id" not in cols:
        alters.append("ALTER TABLE triples ADD COLUMN subject_entity_id TEXT")
    if "object_entity_id" not in cols:
        alters.append("ALTER TABLE triples ADD COLUMN object_entity_id TEXT")
    for sql in alters:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as e:
            logger.warning("triples migration skip: %s — %s", sql, e)
    conn.commit()


def _migrate_novels_columns_before_schema_script(conn: sqlite3.Connection) -> None:
    """旧库在 executescript 之前补齐 novels 列，避免 IF NOT EXISTS 跳过建表后索引引用缺列失败。"""
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='novels' LIMIT 1"
    )
    if cur.fetchone() is None:
        return
    cur = conn.execute("PRAGMA table_info(novels)")
    cols = {row[1] for row in cur.fetchall()}
    migrations = {
        "author": "ALTER TABLE novels ADD COLUMN author TEXT DEFAULT '未知作者'",
        "premise": "ALTER TABLE novels ADD COLUMN premise TEXT DEFAULT ''",
        "target_chapters": "ALTER TABLE novels ADD COLUMN target_chapters INTEGER DEFAULT 0",
        "created_at": (
            "ALTER TABLE novels ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ),
        "updated_at": (
            "ALTER TABLE novels ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ),
        "autopilot_status": (
            "ALTER TABLE novels ADD COLUMN autopilot_status TEXT DEFAULT 'stopped'"
        ),
        "current_stage": (
            "ALTER TABLE novels ADD COLUMN current_stage TEXT DEFAULT 'planning'"
        ),
        "current_act": "ALTER TABLE novels ADD COLUMN current_act INTEGER DEFAULT 0",
        "current_chapter_in_act": (
            "ALTER TABLE novels ADD COLUMN current_chapter_in_act INTEGER DEFAULT 0"
        ),
        "max_auto_chapters": (
            "ALTER TABLE novels ADD COLUMN max_auto_chapters INTEGER DEFAULT 9999"
        ),
        "current_auto_chapters": (
            "ALTER TABLE novels ADD COLUMN current_auto_chapters INTEGER DEFAULT 0"
        ),
        "last_chapter_tension": (
            "ALTER TABLE novels ADD COLUMN last_chapter_tension INTEGER DEFAULT 0"
        ),
        "consecutive_error_count": (
            "ALTER TABLE novels ADD COLUMN consecutive_error_count INTEGER DEFAULT 0"
        ),
        "current_beat_index": (
            "ALTER TABLE novels ADD COLUMN current_beat_index INTEGER DEFAULT 0"
        ),
    }
    for col, sql in migrations.items():
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info("novels pre-schema migration: added column %s", col)
            except sqlite3.OperationalError as e:
                logger.warning("novels pre-schema migration skip %s: %s", col, e)
    cur = conn.execute("PRAGMA table_info(novels)")
    cols_after = {row[1] for row in cur.fetchall()}
    if "slug" not in cols_after:
        try:
            conn.execute("ALTER TABLE novels ADD COLUMN slug TEXT")
            logger.info("novels pre-schema migration: added column slug")
        except sqlite3.OperationalError as e:
            logger.warning("novels pre-schema migration skip slug: %s", e)
    try:
        conn.execute(
            "UPDATE novels SET slug = id WHERE slug IS NULL OR trim(COALESCE(slug, '')) = ''"
        )
    except sqlite3.OperationalError as e:
        logger.warning("novels slug backfill skip: %s", e)
    conn.commit()


def _apply_autopilot_v2_migrations(conn: sqlite3.Connection) -> None:
    """为 novels 表补齐自动驾驶 v2 护城河字段（幂等）"""
    cur = conn.execute("PRAGMA table_info(novels)")
    cols = {row[1] for row in cur.fetchall()}
    migrations = {
        "max_auto_chapters": "ALTER TABLE novels ADD COLUMN max_auto_chapters INTEGER DEFAULT 9999",
        "current_auto_chapters": "ALTER TABLE novels ADD COLUMN current_auto_chapters INTEGER DEFAULT 0",
        "last_chapter_tension": "ALTER TABLE novels ADD COLUMN last_chapter_tension INTEGER DEFAULT 0",
        "consecutive_error_count": "ALTER TABLE novels ADD COLUMN consecutive_error_count INTEGER DEFAULT 0",
        "current_beat_index": "ALTER TABLE novels ADD COLUMN current_beat_index INTEGER DEFAULT 0",
    }
    for col, sql in migrations.items():
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info(f"Added column: {col}")
            except sqlite3.OperationalError as e:
                logger.warning(f"Migration skip {col}: {e}")
    conn.commit()


def _apply_last_chapter_audit_columns(conn: sqlite3.Connection) -> None:
    """章末审阅快照（全托管 AUDITING 后写入，供状态 API 与前台章节状态展示）。"""
    cur = conn.execute("PRAGMA table_info(novels)")
    cols = {row[1] for row in cur.fetchall()}
    migrations = {
        "last_audit_chapter_number": (
            "ALTER TABLE novels ADD COLUMN last_audit_chapter_number INTEGER"
        ),
        "last_audit_similarity": "ALTER TABLE novels ADD COLUMN last_audit_similarity REAL",
        "last_audit_drift_alert": (
            "ALTER TABLE novels ADD COLUMN last_audit_drift_alert INTEGER DEFAULT 0"
        ),
        "last_audit_narrative_ok": (
            "ALTER TABLE novels ADD COLUMN last_audit_narrative_ok INTEGER DEFAULT 1"
        ),
        "last_audit_at": "ALTER TABLE novels ADD COLUMN last_audit_at TEXT",
        # 章后管线状态
        "last_audit_vector_stored": (
            "ALTER TABLE novels ADD COLUMN last_audit_vector_stored INTEGER DEFAULT 0"
        ),
        "last_audit_foreshadow_stored": (
            "ALTER TABLE novels ADD COLUMN last_audit_foreshadow_stored INTEGER DEFAULT 0"
        ),
        "last_audit_triples_extracted": (
            "ALTER TABLE novels ADD COLUMN last_audit_triples_extracted INTEGER DEFAULT 0"
        ),
        "last_audit_quality_scores": (
            "ALTER TABLE novels ADD COLUMN last_audit_quality_scores TEXT"
        ),
        "last_audit_issues": (
            "ALTER TABLE novels ADD COLUMN last_audit_issues TEXT"
        ),
        "target_words_per_chapter": (
            "ALTER TABLE novels ADD COLUMN target_words_per_chapter INTEGER DEFAULT 3500"
        ),
    }
    for col, sql in migrations.items():
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info("novels migration: added column %s", col)
            except sqlite3.OperationalError as e:
                logger.warning("novels migration skip %s: %s", col, e)
    conn.commit()


def _apply_character_enhancements(conn: sqlite3.Connection) -> None:
    """为 bible_characters 表补齐角色增强字段（Task 13/14）"""
    cur = conn.execute("PRAGMA table_info(bible_characters)")
    cols = {row[1] for row in cur.fetchall()}
    migrations = {
        "mental_state": "ALTER TABLE bible_characters ADD COLUMN mental_state TEXT DEFAULT 'NORMAL'",
        "mental_state_reason": "ALTER TABLE bible_characters ADD COLUMN mental_state_reason TEXT DEFAULT ''",
        "verbal_tic": "ALTER TABLE bible_characters ADD COLUMN verbal_tic TEXT DEFAULT ''",
        "idle_behavior": "ALTER TABLE bible_characters ADD COLUMN idle_behavior TEXT DEFAULT ''",
    }
    for col, sql in migrations.items():
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info(f"Added character field: {col}")
            except sqlite3.OperationalError as e:
                logger.warning(f"Character migration skip {col}: {e}")
    conn.commit()


def _apply_chapter_summaries_enhancements(conn: sqlite3.Connection) -> None:
    """为 chapter_summaries 表补齐节拍和摘要扩展字段"""
    cur = conn.execute("PRAGMA table_info(chapter_summaries)")
    cols = {row[1] for row in cur.fetchall()}
    migrations = {
        "key_events": "ALTER TABLE chapter_summaries ADD COLUMN key_events TEXT",
        "open_threads": "ALTER TABLE chapter_summaries ADD COLUMN open_threads TEXT",
        "consistency_note": "ALTER TABLE chapter_summaries ADD COLUMN consistency_note TEXT",
        "beat_sections": "ALTER TABLE chapter_summaries ADD COLUMN beat_sections TEXT",
        "micro_beats": "ALTER TABLE chapter_summaries ADD COLUMN micro_beats TEXT",
        "sync_status": "ALTER TABLE chapter_summaries ADD COLUMN sync_status TEXT DEFAULT 'draft'",
    }
    for col, sql in migrations.items():
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info(f"Added chapter_summaries field: {col}")
            except sqlite3.OperationalError as e:
                logger.warning(f"chapter_summaries migration skip {col}: {e}")
    conn.commit()



def _apply_migration_files(conn: sqlite3.Connection) -> None:
    """应用独立的迁移文件（幂等执行）"""
    migrations_dir = Path(__file__).parent / "migrations"
    
    # 按执行顺序定义迁移文件
    migration_files = [
        "add_macro_diagnosis_results.sql",
        "add_micro_beats_to_chapter_summaries.sql",
    ]
    
    for migration_file in migration_files:
        migration_path = migrations_dir / migration_file
        if migration_path.exists():
            try:
                with open(migration_path, 'r', encoding='utf-8') as f:
                    migration_sql = f.read()
                
                # 执行迁移SQL（使用executescript处理多个语句）
                conn.executescript(migration_sql)
                conn.commit()
                logger.info(f"Applied migration: {migration_file}")
            except sqlite3.OperationalError as e:
                # 忽略已存在的表/列错误（幂等性）
                if "already exists" in str(e) or "duplicate column" in str(e):
                    logger.debug(f"Migration {migration_file} already applied: {e}")
                else:
                    logger.warning(f"Migration {migration_file} failed: {e}")
            except Exception as e:
                logger.warning(f"Failed to apply migration {migration_file}: {e}")
        else:
            logger.warning(f"Migration file not found: {migration_path}")


def _ensure_triple_provenance_table(conn: sqlite3.Connection) -> None:
    """旧库补齐 triple_provenance 表（schema.sql 对新库已包含）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS triple_provenance (
            id TEXT PRIMARY KEY,
            triple_id TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            story_node_id TEXT,
            chapter_element_id TEXT,
            rule_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'primary',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (triple_id) REFERENCES triples(id) ON DELETE CASCADE,
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_triple_provenance_triple ON triple_provenance(triple_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_triple_provenance_novel ON triple_provenance(novel_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_triple_provenance_story_node ON triple_provenance(story_node_id)"
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_triple_provenance_with_element
        ON triple_provenance (triple_id, rule_id, story_node_id, chapter_element_id)
        WHERE chapter_element_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_triple_provenance_null_element
        ON triple_provenance (triple_id, rule_id, IFNULL(story_node_id, ''))
        WHERE chapter_element_id IS NULL
        """
    )
    conn.commit()


class DatabaseConnection:
    """SQLite 数据库连接管理器（线程本地存储，每线程独立连接）"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._ensure_database_exists()

    def _ensure_database_exists(self) -> None:
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            _migrate_novels_columns_before_schema_script(conn)
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
                conn.executescript(schema_sql)
                conn.commit()
                logger.info(f"Database initialized at {self.db_path}")
        else:
            logger.warning(f"Schema file not found: {schema_path}")

        _migrate_triples_columns(conn)
        _apply_autopilot_v2_migrations(conn)
        _apply_last_chapter_audit_columns(conn)
        _apply_character_enhancements(conn)
        _apply_chapter_summaries_enhancements(conn)
        _ensure_triple_provenance_table(conn)
        _apply_migration_files(conn)
        conn.close()

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA busy_timeout=5000")
        return self._local.connection

    @contextmanager
    def transaction(self):
        """事务上下文管理器

        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT INTO ...")
                conn.execute("UPDATE ...")
        """
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL 语句

        Args:
            sql: SQL 语句
            params: 参数元组

        Returns:
            Cursor 对象
        """
        conn = self.get_connection()
        return conn.execute(sql, params)

    def execute_many(self, sql: str, params_list: list) -> None:
        """批量执行 SQL 语句

        Args:
            sql: SQL 语句
            params_list: 参数列表
        """
        conn = self.get_connection()
        conn.executemany(sql, params_list)
        conn.commit()

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """查询单条记录

        Args:
            sql: SQL 语句
            params: 参数元组

        Returns:
            字典格式的记录，如果不存在返回 None
        """
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """查询多条记录

        Args:
            sql: SQL 语句
            params: 参数元组

        Returns:
            字典列表
        """
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None
            logger.info("Database connection closed (thread-local)")


# 全局数据库实例
_db_instance: Optional[DatabaseConnection] = None


def get_database(db_path: Optional[str] = None) -> DatabaseConnection:
    """获取全局数据库实例（默认使用仓库内 data/aitext.db 绝对路径）。"""
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            from application.paths import get_db_path

            db_path = get_db_path()
        _db_instance = DatabaseConnection(db_path)
    return _db_instance
