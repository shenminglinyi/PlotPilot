"""各入口共用的 SQLite PRAGMA，避免零散 connect 遗漏 busy_timeout/WAL 导致 database is locked。"""

import sqlite3

# 与 DatabaseConnection.get_connection 对齐；SQLite busy_handler 毫秒
BUSY_TIMEOUT_MS = 30000


def apply_standard_pragmas(conn: sqlite3.Connection) -> None:
    """在 sqlite3.connect 之后立刻调用（单连接、连接池、短连接均需）。"""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA cache_size=-32768")
