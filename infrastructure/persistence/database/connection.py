"""SQLite 数据库连接"""
import logging
import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from infrastructure.persistence.database.sqlite_pragmas import (
    BUSY_TIMEOUT_MS,
    apply_standard_pragmas,
)

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
        "beats_completed": (
            "ALTER TABLE novels ADD COLUMN beats_completed INTEGER DEFAULT 0"
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


def _apply_bible_character_four_d_sqlite(conn: sqlite3.Connection) -> None:
    """Bible 人物：四维心理与 POV 扩展列（与引擎 T0 / 工作台锚点对齐）。"""
    cur = conn.execute("PRAGMA table_info(bible_characters)")
    cols = {row[1] for row in cur.fetchall()}
    migrations = {
        "core_belief": "ALTER TABLE bible_characters ADD COLUMN core_belief TEXT NOT NULL DEFAULT ''",
        "moral_taboos_json": "ALTER TABLE bible_characters ADD COLUMN moral_taboos_json TEXT NOT NULL DEFAULT '[]'",
        "voice_profile_json": "ALTER TABLE bible_characters ADD COLUMN voice_profile_json TEXT NOT NULL DEFAULT '{}'",
        "active_wounds_json": "ALTER TABLE bible_characters ADD COLUMN active_wounds_json TEXT NOT NULL DEFAULT '[]'",
        "public_profile": "ALTER TABLE bible_characters ADD COLUMN public_profile TEXT NOT NULL DEFAULT ''",
        "hidden_profile": "ALTER TABLE bible_characters ADD COLUMN hidden_profile TEXT NOT NULL DEFAULT ''",
        "reveal_chapter": "ALTER TABLE bible_characters ADD COLUMN reveal_chapter INTEGER",
    }
    for col, sql in migrations.items():
        if col not in cols:
            try:
                conn.execute(sql)
                logger.info("bible_characters migration: added column %s", col)
            except sqlite3.OperationalError as e:
                logger.warning("bible_characters migration skip %s: %s", col, e)
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


def _apply_chapters_word_count_migration(conn: sqlite3.Connection) -> None:
    """为 chapters 表补齐 word_count 列（persistence_queue 依赖此列）"""
    cur = conn.execute("PRAGMA table_info(chapters)")
    cols = {row[1] for row in cur.fetchall()}
    if "word_count" not in cols:
        try:
            conn.execute("ALTER TABLE chapters ADD COLUMN word_count INTEGER DEFAULT 0")
            logger.info("chapters migration: added column word_count")
        except sqlite3.OperationalError as e:
            logger.warning("chapters migration skip word_count: %s", e)
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
    """应用 migrations 目录下全部 .sql（幂等执行，顺序按文件名稳定排序）。

    优化：使用 migrations_applied 表跟踪已应用的迁移，避免重复执行。
    """
    # 尝试创建迁移跟踪表（如果不存在），带重试和错误处理
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migrations_applied (
                    migration_file TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            break
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logger.warning(f"Database locked, retrying... (attempt {attempt + 1}/{max_retries})")
                import time
                time.sleep(0.5 * (attempt + 1))  # 递增等待时间
                continue
            elif "already exists" in str(e):
                break  # 表已存在，继续
            else:
                # 如果无法创建跟踪表，回退到旧逻辑
                logger.warning(f"Cannot create migrations_applied table: {e}, using legacy mode")
                _apply_migration_files_legacy(conn)
                return

    # 获取已应用的迁移列表
    applied = set()
    try:
        cursor = conn.execute("SELECT migration_file FROM migrations_applied")
        applied = {row[0] for row in cursor.fetchall()}
    except Exception:
        pass  # 表不存在，继续执行

    migrations_dir = _database_asset_dir() / "migrations"
    if not migrations_dir.is_dir():
        logger.warning("未找到迁移目录（将仅依赖 schema.sql 与代码内补丁）: %s", migrations_dir)
        return

    new_migrations = 0
    for migration_path in sorted(migrations_dir.glob("*.sql")):
        migration_file = migration_path.name

        # 跳过已应用的迁移
        if migration_file in applied:
            continue

        try:
            migration_sql = migration_path.read_text(encoding="utf-8")
            conn.executescript(migration_sql)
            conn.execute(
                "INSERT OR IGNORE INTO migrations_applied (migration_file) VALUES (?)",
                (migration_file,)
            )
            conn.commit()
            logger.info("Applied migration: %s", migration_file)
            new_migrations += 1
        except sqlite3.OperationalError as e:
            err_str = str(e)
            if "already exists" in err_str or "duplicate column" in err_str:
                # 即使失败也记录为已应用，避免下次重试
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO migrations_applied (migration_file) VALUES (?)",
                        (migration_file,)
                    )
                    conn.commit()
                except:
                    pass
                logger.debug("Migration %s already applied: %s", migration_file, e)
            elif "no such function" in err_str:
                # SQLite 不支持的函数（如 content()），标记为已应用避免反复报错
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO migrations_applied (migration_file) VALUES (?)",
                        (migration_file,)
                    )
                    conn.commit()
                except:
                    pass
                logger.warning(
                    "Migration %s uses unsupported SQLite function, marking as applied: %s",
                    migration_file, e
                )
            else:
                logger.warning("Migration %s failed: %s", migration_file, e)
        except Exception as e:
            logger.warning("Failed to apply migration %s: %s", migration_file, e)

    if new_migrations == 0 and applied:
        logger.debug("All %d migrations already applied, skipped", len(applied))


def _apply_migration_files_legacy(conn: sqlite3.Connection) -> None:
    """旧版迁移逻辑（无跟踪表，每次都尝试执行所有迁移）。"""
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


class DatabaseConnection:
    """SQLite 数据库连接管理器（线程本地存储，每线程独立连接）

    改进：
    - 定期 WAL checkpoint（每 20 次写操作自动触发），防止 WAL 文件无限增长
    - 应用关闭时 close_all() 清理所有线程连接
    """

    # WAL checkpoint 阈值：每 N 次写操作触发一次 PRAGMA wal_checkpoint(TRUNCATE)
    _WAL_CHECKPOINT_INTERVAL = 20

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._write_counter = 0
        self._write_counter_lock = threading.Lock()
        # 记录所有线程连接，以便 close_all() 时统一清理
        self._all_connections: list[sqlite3.Connection] = []
        self._all_connections_lock = threading.Lock()
        self._ensure_database_exists()

    def _ensure_database_exists(self) -> None:
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        apply_standard_pragmas(conn)

        schema_path = _database_asset_dir() / "schema.sql"
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
        _apply_bible_character_four_d_sqlite(conn)
        _apply_chapter_summaries_enhancements(conn)
        _apply_chapters_word_count_migration(conn)
        _ensure_triple_provenance_table(conn)
        _apply_migration_files(conn)
        conn.close()

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
            conn.row_factory = sqlite3.Row
            apply_standard_pragmas(conn)
            self._local.connection = conn
            with self._all_connections_lock:
                self._all_connections.append(conn)
        return self._local.connection

    @contextmanager
    def transaction(self):
        """事务：持久化消费者在 writer 线程上直连；其它线程收集为一条 TXN_BATCH 入队。"""
        from infrastructure.persistence.database.write_dispatch import (
            TxnCollectingConnection,
            allow_direct_sqlite_writes,
            enqueue_txn_batch,
            is_sqlite_writer_thread,
        )

        if allow_direct_sqlite_writes() or is_sqlite_writer_thread():
            conn = self.get_connection()
            try:
                yield conn
                conn.commit()
                self._maybe_checkpoint()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction failed: {e}")
                raise
            return

        collector = TxnCollectingConnection()
        try:
            yield collector
        except Exception:
            raise
        else:
            if collector.operations and not enqueue_txn_batch(collector.operations):
                raise RuntimeError("持久化队列未就绪，事务未能入队")

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        from infrastructure.persistence.database.write_dispatch import (
            _EnqueuedStmtCursor,
            allow_direct_sqlite_writes,
            enqueue_execute_sql,
            is_sqlite_writer_thread,
            sql_is_mutating,
        )

        if (
            sql_is_mutating(sql)
            and not allow_direct_sqlite_writes()
            and not is_sqlite_writer_thread()
        ):
            plist = list(params) if params else []
            if not enqueue_execute_sql(sql, plist):
                raise RuntimeError("持久化队列未就绪，写 SQL 未能入队")
            return _EnqueuedStmtCursor()  # type: ignore[return-value]

        conn = self.get_connection()
        return conn.execute(sql, params)

    def execute_many(self, sql: str, params_list: list) -> None:
        from infrastructure.persistence.database.write_dispatch import (
            allow_direct_sqlite_writes,
            enqueue_txn_batch,
            is_sqlite_writer_thread,
            sql_is_mutating,
        )

        if not params_list:
            return
        if (
            sql_is_mutating(sql)
            and not allow_direct_sqlite_writes()
            and not is_sqlite_writer_thread()
        ):
            ops = []
            for p in params_list:
                tup = tuple(p) if not isinstance(p, tuple) else p
                ops.append((sql, tup))
            if not enqueue_txn_batch(ops):
                raise RuntimeError("持久化队列未就绪，批量写未能入队")
            return

        conn = self.get_connection()
        conn.executemany(sql, params_list)
        conn.commit()
        self._maybe_checkpoint()

    def commit(self) -> None:
        """提交当前线程连接上的事务；非 writer 上的变更已由队列消费者提交，此处仅 writer 落 commit + checkpoint。"""
        from infrastructure.persistence.database.write_dispatch import (
            allow_direct_sqlite_writes,
            is_sqlite_writer_thread,
        )

        if allow_direct_sqlite_writes() or is_sqlite_writer_thread():
            self.get_connection().commit()
            self._maybe_checkpoint()

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
        """关闭当前线程的数据库连接。"""
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            conn = self._local.connection
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            conn.close()
            with self._all_connections_lock:
                try:
                    self._all_connections.remove(conn)
                except ValueError:
                    pass
            self._local.connection = None
            logger.info("Database connection closed (thread-local)")

    def close_all(self, skip_checkpoint: bool = False) -> None:
        """关闭所有线程的数据库连接（应用关闭时调用）。

        Args:
            skip_checkpoint: 跳过 WAL checkpoint（关闭时 DB 可能被守护进程锁住，
                checkpoint 会无限等待导致进程卡死）。WAL 模式下不 checkpoint
                只会导致 WAL 文件稍大，下次启动时会自动恢复。
        """
        with self._all_connections_lock:
            connections = list(self._all_connections)
            self._all_connections.clear()
        for conn in connections:
            if not skip_checkpoint:
                try:
                    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
            try:
                conn.close()
            except Exception:
                pass
        logger.info("All database connections closed (%d, skip_checkpoint=%s)", len(connections), skip_checkpoint)

    def _maybe_checkpoint(self) -> None:
        """定期 WAL checkpoint：每 _WAL_CHECKPOINT_INTERVAL 次写操作触发 TRUNCATE。"""
        with self._write_counter_lock:
            self._write_counter += 1
            if self._write_counter < self._WAL_CHECKPOINT_INTERVAL:
                return
            self._write_counter = 0
        try:
            conn = self.get_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.debug("WAL checkpoint triggered (interval=%d)", self._WAL_CHECKPOINT_INTERVAL)
        except Exception as e:
            logger.debug("WAL checkpoint skipped: %s", e)


# 全局数据库实例
_db_instance: Optional[DatabaseConnection] = None

# 全局连接池实例
_connection_pool_instance: Optional["SQLiteConnectionPool"] = None


def get_database(db_path: Optional[str] = None) -> DatabaseConnection:
    """获取全局数据库实例（默认使用仓库内 data/plotpilot.db 绝对路径）。"""
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            from application.paths import get_db_path

            db_path = get_db_path()
        _db_instance = DatabaseConnection(db_path)
    return _db_instance


def get_connection_pool(db_path: Optional[str] = None):
    """获取全局连接池实例（推荐使用）。

    优势：
    - 连接复用，避免频繁创建/销毁
    - 短连接模式，降低持锁时间
    - 更好的并发性能
    """
    global _connection_pool_instance
    if _connection_pool_instance is None:
        if db_path is None:
            from application.paths import get_db_path
            db_path = get_db_path()

        from infrastructure.persistence.database.connection_pool import SQLiteConnectionPool
        _connection_pool_instance = SQLiteConnectionPool(db_path)
        _connection_pool_instance.initialize()

    return _connection_pool_instance
