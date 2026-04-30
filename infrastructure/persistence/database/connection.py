"""SQLite 数据库连接"""
import logging
import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _database_asset_dir() -> Path:
    """
    存放 schema.sql 与 migrations/ 的目录。

    - 开发：本仓库 infrastructure/persistence/database/
    - PyInstaller：始终使用包内资源（sys._MEIPASS），不读开发者本机其它路径。
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "infrastructure" / "persistence" / "database"
    return Path(__file__).resolve().parent


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
            "ALTER TABLE novels ADD COLUMN target_words_per_chapter INTEGER DEFAULT 2500"
        ),
        "audit_progress": (
            "ALTER TABLE novels ADD COLUMN audit_progress TEXT"
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


def _migrate_topic_ideas_report_columns(conn: sqlite3.Connection) -> None:
    """为已存在的 topic_ideas 表补齐当前选题立项列（幂等）。"""
    cur = conn.execute("PRAGMA table_info(topic_ideas)")
    cols = {row[1] for row in cur.fetchall()}
    if not cols:
        return
    migrations = {
        "status": "ALTER TABLE topic_ideas ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'",
        "genre": "ALTER TABLE topic_ideas ADD COLUMN genre TEXT DEFAULT ''",
        "world_preset": "ALTER TABLE topic_ideas ADD COLUMN world_preset TEXT DEFAULT ''",
        "length_tier": "ALTER TABLE topic_ideas ADD COLUMN length_tier TEXT DEFAULT ''",
        "logline": "ALTER TABLE topic_ideas ADD COLUMN logline TEXT DEFAULT ''",
        "premise": "ALTER TABLE topic_ideas ADD COLUMN premise TEXT DEFAULT ''",
        "protagonist_hook": "ALTER TABLE topic_ideas ADD COLUMN protagonist_hook TEXT DEFAULT ''",
        "core_conflict": "ALTER TABLE topic_ideas ADD COLUMN core_conflict TEXT DEFAULT ''",
        "opening_hook": "ALTER TABLE topic_ideas ADD COLUMN opening_hook TEXT DEFAULT ''",
        "selling_points_json": "ALTER TABLE topic_ideas ADD COLUMN selling_points_json TEXT DEFAULT '[]'",
        "long_term_potential": "ALTER TABLE topic_ideas ADD COLUMN long_term_potential TEXT DEFAULT ''",
        "risk_notes_json": "ALTER TABLE topic_ideas ADD COLUMN risk_notes_json TEXT DEFAULT '[]'",
        "market_tags_json": "ALTER TABLE topic_ideas ADD COLUMN market_tags_json TEXT DEFAULT '[]'",
        "score": "ALTER TABLE topic_ideas ADD COLUMN score INTEGER DEFAULT 0",
        "adopted_novel_id": "ALTER TABLE topic_ideas ADD COLUMN adopted_novel_id TEXT",
        "source_brief_json": "ALTER TABLE topic_ideas ADD COLUMN source_brief_json TEXT DEFAULT '{}'",
        "development_notes_json": (
            "ALTER TABLE topic_ideas ADD COLUMN development_notes_json TEXT DEFAULT '{}'"
        ),
        "evaluation_json": (
            "ALTER TABLE topic_ideas ADD COLUMN evaluation_json TEXT DEFAULT '{}'"
        ),
        "created_at": "ALTER TABLE topic_ideas ADD COLUMN created_at TIMESTAMP DEFAULT ''",
        "updated_at": "ALTER TABLE topic_ideas ADD COLUMN updated_at TIMESTAMP DEFAULT ''",
    }
    for col, sql in migrations.items():
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info("topic_ideas migration: added column %s", col)
            except sqlite3.OperationalError as e:
                logger.warning("topic_ideas migration skip %s: %s", col, e)
    conn.commit()


def _ensure_topic_market_signal_settings_table(conn: sqlite3.Connection) -> None:
    """旧库补齐市场信号自动采集配置表。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_market_signal_settings (
            id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            interval_minutes INTEGER NOT NULL DEFAULT 180,
            limit_per_source INTEGER NOT NULL DEFAULT 8,
            lookback_days INTEGER NOT NULL DEFAULT 30,
            source_weights_json TEXT DEFAULT '{}',
            selected_source_keys_json TEXT DEFAULT '[]',
            last_run_at TEXT DEFAULT '',
            last_status TEXT DEFAULT 'idle',
            last_error TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _ensure_topic_market_signal_credentials_table(conn: sqlite3.Connection) -> None:
    """旧库补齐市场信号来源凭据配置表。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_market_signal_credentials (
            source_key TEXT PRIMARY KEY,
            api_key TEXT DEFAULT '',
            cookie TEXT DEFAULT '',
            endpoint_url TEXT DEFAULT '',
            headers_json TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(topic_market_signal_credentials)").fetchall()}
    if "endpoint_url" not in cols:
        conn.execute("ALTER TABLE topic_market_signal_credentials ADD COLUMN endpoint_url TEXT DEFAULT ''")
    conn.commit()


def _ensure_topic_market_signal_source_health_table(conn: sqlite3.Connection) -> None:
    """旧库补齐市场信号来源健康状态表。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_market_signal_source_health (
            source_key TEXT PRIMARY KEY,
            status TEXT DEFAULT 'unknown',
            last_run_at TEXT DEFAULT '',
            last_success_at TEXT DEFAULT '',
            last_count INTEGER DEFAULT 0,
            last_error TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _ensure_style_bible_tables(conn: sqlite3.Connection) -> None:
    """旧库补齐写作手法知识库表。"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS style_samples (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL DEFAULT '',
            profile_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'reference',
            genre TEXT NOT NULL DEFAULT '',
            scene_type TEXT NOT NULL DEFAULT '',
            pov TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            char_count INTEGER NOT NULL DEFAULT 0,
            allowed_for_generation INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_style_samples_novel_hash
        ON style_samples(novel_id, content_hash);

        CREATE INDEX IF NOT EXISTS idx_style_samples_novel_profile
        ON style_samples(novel_id, profile_id);

        CREATE TABLE IF NOT EXISTS style_sample_chunks (
            id TEXT PRIMARY KEY,
            sample_id TEXT NOT NULL,
            chunk_type TEXT NOT NULL CHECK(chunk_type IN ('chapter', 'scene', 'paragraph')),
            sequence INTEGER NOT NULL DEFAULT 0,
            chapter_number INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            char_count INTEGER NOT NULL DEFAULT 0,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sample_id) REFERENCES style_samples(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_style_sample_chunks_sample
        ON style_sample_chunks(sample_id, sequence);

        CREATE TABLE IF NOT EXISTS style_profiles (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
            profile_json TEXT NOT NULL DEFAULT '{}',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            rules_json TEXT NOT NULL DEFAULT '[]',
            forbidden_patterns_json TEXT NOT NULL DEFAULT '[]',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_style_profiles_novel_status
        ON style_profiles(novel_id, status);

        CREATE TABLE IF NOT EXISTS style_technique_cards (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            scene_type TEXT NOT NULL DEFAULT '',
            rule_text TEXT NOT NULL,
            example_summary TEXT NOT NULL DEFAULT '',
            prompt_instruction TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            weight REAL NOT NULL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_id) REFERENCES style_profiles(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_style_technique_cards_profile_enabled
        ON style_technique_cards(profile_id, enabled);
        """
    )
    conn.commit()



def _apply_migration_files(conn: sqlite3.Connection) -> None:
    """应用 migrations 目录下全部 .sql（幂等执行，顺序按文件名稳定排序）。"""
    migrations_dir = _database_asset_dir() / "migrations"
    if not migrations_dir.is_dir():
        logger.warning("未找到迁移目录（将仅依赖 schema.sql 与代码内补丁）: %s", migrations_dir)
        return

    for migration_path in sorted(migrations_dir.glob("*.sql")):
        migration_file = migration_path.name
        try:
            migration_sql = migration_path.read_text(encoding="utf-8")
            conn.executescript(migration_sql)
            conn.commit()
            logger.info("Applied migration: %s", migration_file)
        except sqlite3.OperationalError as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                logger.debug("Migration %s already applied: %s", migration_file, e)
            else:
                logger.warning("Migration %s failed: %s", migration_file, e)
        except OSError as e:
            logger.warning("Failed to read migration %s: %s", migration_file, e)
        except Exception as e:
            logger.warning("Failed to apply migration %s: %s", migration_file, e)


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


def _ensure_external_model_tasks_table(conn: sqlite3.Connection) -> None:
    """补齐外部模型任务台账，并迁移掉早期误加的 chapter 外键。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_model_tasks (
            id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            prompt TEXT NOT NULL DEFAULT '',
            instruction TEXT NOT NULL DEFAULT '',
            source_draft_id TEXT NOT NULL DEFAULT '',
            candidate_draft_id TEXT NOT NULL DEFAULT '',
            response_preview TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'prompted',
            execution_mode TEXT NOT NULL DEFAULT 'copy_paste',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        )
        """
    )
    fk_rows = conn.execute("PRAGMA foreign_key_list(external_model_tasks)").fetchall()
    has_chapter_fk = any(str(row[2]) == "chapters" for row in fk_rows)
    if has_chapter_fk:
        conn.execute("ALTER TABLE external_model_tasks RENAME TO external_model_tasks_old")
        conn.execute(
            """
            CREATE TABLE external_model_tasks (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                instruction TEXT NOT NULL DEFAULT '',
                source_draft_id TEXT NOT NULL DEFAULT '',
                candidate_draft_id TEXT NOT NULL DEFAULT '',
                response_preview TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'prompted',
                execution_mode TEXT NOT NULL DEFAULT 'copy_paste',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            INSERT INTO external_model_tasks (
                id, novel_id, chapter_number, model, prompt, instruction,
                source_draft_id, candidate_draft_id, response_preview,
                status, execution_mode, created_at, updated_at
            )
            SELECT
                id, novel_id, chapter_number, model, prompt, instruction,
                source_draft_id, candidate_draft_id, response_preview,
                status, execution_mode, created_at, updated_at
            FROM external_model_tasks_old
            """
        )
        conn.execute("DROP TABLE external_model_tasks_old")
        logger.info("external_model_tasks migration: removed chapter foreign key")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_model_tasks_novel_chapter
        ON external_model_tasks(novel_id, chapter_number, updated_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_model_tasks_candidate
        ON external_model_tasks(novel_id, candidate_draft_id)
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

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row

        schema_path = _database_asset_dir() / "schema.sql"
        if schema_path.exists():
            _migrate_novels_columns_before_schema_script(conn)
            _migrate_topic_ideas_report_columns(conn)
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
        _migrate_topic_ideas_report_columns(conn)
        _ensure_topic_market_signal_settings_table(conn)
        _ensure_topic_market_signal_credentials_table(conn)
        _ensure_topic_market_signal_source_health_table(conn)
        _ensure_style_bible_tables(conn)
        _ensure_triple_provenance_table(conn)
        _ensure_external_model_tasks_table(conn)
        _apply_migration_files(conn)
        conn.close()

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            # 与 API/守护进程并发写时延长等待（毫秒）
            self._local.connection.execute("PRAGMA busy_timeout=30000")
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

    def commit(self) -> None:
        """提交当前线程连接上的事务（与 execute() 成对使用）。"""
        self.get_connection().commit()

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
