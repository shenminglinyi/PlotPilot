"""单写者内核：标记持久化队列消费线程，并对「非 writer 线程」提供入队封装。

SQLite 单机多写竞争者全部经 mp.Queue → 单一消费者线程顺序提交，从源头消除 database is locked。"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import threading
from typing import Any, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

_sqlite_writer_thread_ident: Optional[int] = None

# interfaces.main startup：在持久化消费者线程就绪之前允许直连 SQLite（见 startup_sqlite_writes_bypass_queue）
_startup_sqlite_bootstrap_depth = 0


def register_sqlite_writer_thread() -> None:
    global _sqlite_writer_thread_ident
    _sqlite_writer_thread_ident = threading.get_ident()


def clear_sqlite_writer_thread() -> None:
    global _sqlite_writer_thread_ident
    _sqlite_writer_thread_ident = None


def is_sqlite_writer_thread() -> bool:
    return (
        _sqlite_writer_thread_ident is not None
        and threading.get_ident() == _sqlite_writer_thread_ident
    )


@contextlib.contextmanager
def startup_sqlite_writes_bypass_queue():
    """在持久化消费者线程启动前，临时允许调用方线程直连 SQLite（启动钩子专用）。

    典型用法：`interfaces.main` 中先于 `_bootstrap_persistence_consumer_early()` 复位运行中标志，
    避免「writer + 主线程第二连接」在异常锁竞争下卡住整个 busy_timeout（默认可达 30s）。

    注意：上下文内不要使用 ``await``，也不要在已进入消费者循环后套用。
    """
    global _startup_sqlite_bootstrap_depth
    _startup_sqlite_bootstrap_depth += 1
    try:
        yield
    finally:
        _startup_sqlite_bootstrap_depth -= 1


def allow_direct_sqlite_writes() -> bool:
    """脚本 / 迁移 / 启动早期 bypass / 个别单测可走直连写库；正式运行时默认走队列。"""
    if _startup_sqlite_bootstrap_depth > 0:
        return True
    v = os.environ.get("AITEXT_ALLOW_DIRECT_SQLITE_WRITES", "").strip().lower()
    return v in ("1", "true", "yes")


def strip_sql_comments(sql: str) -> str:
    text = re.sub(r"--[^\n]*", "", sql)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def sql_is_mutating(sql: str) -> bool:
    s = strip_sql_comments(sql).strip().upper()
    if not s:
        return False
    if s.startswith("WITH"):
        return bool(re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", s))
    tok = s.split()[0]
    non_mutating = frozenset(
        {
            "SELECT",
            "EXPLAIN",
            "PRAGMA",
            "BEGIN",
            "COMMIT",
            "ROLLBACK",
            "SAVEPOINT",
            "RELEASE",
            "END",
        }
    )
    if tok in non_mutating:
        return False
    return True


Params = Union[tuple, list]


class _EnqueuedStmtCursor:
    """非 writer 线程上 execute(INSERT/UPDATE…) 入队后对调用方的最小兼容。"""

    rowcount = 1

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class TxnCollectingConnection:
    """在 API 线程上收集 SQL，退出 `transaction()` 时一次性 EXECUTE_SQL_TXN_BATCH。"""

    def __init__(self) -> None:
        self.operations: List[Tuple[str, tuple]] = []

    def execute(self, sql: str, params: Any = ()) -> _EnqueuedStmtCursor:
        if isinstance(params, list):
            p: tuple = tuple(params)
        elif isinstance(params, tuple):
            p = params
        else:
            p = (params,)
        self.operations.append((sql, p))
        return _EnqueuedStmtCursor()


def enqueue_execute_sql(sql: str, params: Optional[Params] = None) -> bool:
    from application.engine.services.persistence_queue import (
        get_persistence_queue,
        PersistenceCommandType,
    )

    pq = get_persistence_queue()
    if pq is None or pq.get_queue() is None:
        logger.error("持久化队列未就绪，丢弃写 SQL")
        return False
    plist = list(params) if params is not None else []
    return pq.push(
        PersistenceCommandType.EXECUTE_SQL.value,
        {"sql": sql, "params": plist},
    )


def enqueue_txn_batch(
    operations: List[Tuple[str, Params]],
) -> bool:
    """多语句同一 BEGIN IMMEDIATE 事务提交（高性能、原子）。"""
    from application.engine.services.persistence_queue import (
        get_persistence_queue,
        PersistenceCommandType,
    )

    if not operations:
        return True
    pq = get_persistence_queue()
    if pq is None or pq.get_queue() is None:
        logger.error("持久化队列未就绪，丢弃事务批量写")
        return False
    serializable = [
        {"sql": op[0], "params": list(op[1]) if op[1] is not None else []}
        for op in operations
    ]
    return pq.push(
        PersistenceCommandType.EXECUTE_SQL_TXN_BATCH.value,
        {"operations": serializable},
    )


def enqueue_delete_chapter(chapter_db_id: str) -> bool:
    from application.engine.services.persistence_queue import (
        get_persistence_queue,
        PersistenceCommandType,
    )

    pq = get_persistence_queue()
    if pq is None or pq.get_queue() is None:
        return False
    return pq.push(
        PersistenceCommandType.DELETE_CHAPTER.value,
        {"chapter_db_id": chapter_db_id},
    )
