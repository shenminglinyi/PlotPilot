"""监控数据库连接"""
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from infrastructure.monitoring.token_watcher_config import get_monitoring_db_path


class MonitoringDB:
    """monitoring.db 数据库连接（线程安全单例）"""
    _instance: Optional['MonitoringDB'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'MonitoringDB':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            db_path = get_monitoring_db_path()
            self._local.conn = sqlite3.connect(
                str(db_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_schema(self):
        """初始化数据库 schema"""
        conn = self._get_conn()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS token_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                model TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 1,
                error_message TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_token_logs_timestamp ON token_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_token_logs_model ON token_logs(model);
            CREATE INDEX IF NOT EXISTS idx_token_logs_provider ON token_logs(provider);
            
            CREATE TABLE IF NOT EXISTS token_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            
            CREATE TABLE IF NOT EXISTS token_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                total_calls INTEGER NOT NULL DEFAULT 0,
                total_input_tokens INTEGER NOT NULL DEFAULT 0,
                total_output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                total_latency_ms INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(provider, model)
            );
            
            CREATE INDEX IF NOT EXISTS idx_token_stats_provider ON token_stats(provider);
            CREATE INDEX IF NOT EXISTS idx_token_stats_model ON token_stats(model);
        ''')
        conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        return self.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: tuple = ()) -> list:
        return self.execute(sql, params).fetchall()

    def commit(self):
        self._get_conn().commit()

    def get_config(self, key: str, default: str = '') -> str:
        """获取配置值"""
        row = self.fetch_one('SELECT value FROM token_config WHERE key = ?', (key,))
        return row['value'] if row else default

    def set_config(self, key: str, value: str):
        """设置配置值"""
        self.execute(
            '''INSERT OR REPLACE INTO token_config (key, value) VALUES (?, ?)''',
            (key, value)
        )
        self.commit()


def get_monitoring_db() -> MonitoringDB:
    return MonitoringDB()
