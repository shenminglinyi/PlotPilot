"""SQLite 连接池 - 多进程并发优化

解决问题：
1. 长连接持锁时间过长（3-5秒）
2. 多进程竞争导致 API 超时
3. Checkpoint 阻塞所有读写

优化方案：
1. 连接池：预创建连接，按需借用
2. 短连接：快速释放，降低持锁时间
3. WAL checkpoint 优化：减少阻塞
"""
import logging
import sqlite3
import threading
import time
import queue
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from infrastructure.persistence.database.sqlite_pragmas import apply_standard_pragmas

logger = logging.getLogger(__name__)


class SQLiteConnectionPool:
    """SQLite 连接池（单进程多线程安全）

    设计原则：
    - 预创建连接，避免频繁创建/销毁
    - 短时间持有连接，快速归还
    - WAL checkpoint 优化，减少阻塞
    """

    # 与 DatabaseConnection 对齐：过短的 busy_timeout 会加重 database is locked 误报
    DEFAULT_POOL_SIZE = 5
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        db_path: str,
        pool_size: int = None,
        timeout: float = None
    ):
        self.db_path = db_path
        self.pool_size = pool_size or self.DEFAULT_POOL_SIZE
        self.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT

        # 连接池队列
        self._pool: queue.Queue = queue.Queue(maxsize=self.pool_size)
        self._lock = threading.RLock()
        self._initialized = False

        # 统计信息
        self._stats = {
            "connections_created": 0,
            "connections_borrowed": 0,
            "connections_returned": 0,
            "wait_time_total": 0.0,
            "wait_count": 0,
        }

        # 确保数据库文件存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def initialize(self):
        """初始化连接池（预创建连接）"""
        with self._lock:
            if self._initialized:
                return

            logger.info(f"初始化 SQLite 连接池: {self.db_path} (size={self.pool_size})")

            for i in range(self.pool_size):
                conn = self._create_connection()
                self._pool.put(conn)
                self._stats["connections_created"] += 1

            self._initialized = True
            logger.info(f"✅ SQLite 连接池初始化完成")

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # 允许跨线程使用
            timeout=self.timeout
        )

        apply_standard_pragmas(conn)
        # 连接池可适当更频繁 checkpoint，与单连接略区分
        conn.execute("PRAGMA wal_autocheckpoint=100")

        conn.row_factory = sqlite3.Row

        return conn

    @contextmanager
    def get_connection(self):
        """获取连接（上下文管理器，自动归还）"""
        if not self._initialized:
            self.initialize()

        conn = None
        wait_start = time.time()

        try:
            # 从池中获取连接
            conn = self._pool.get(timeout=self.timeout)
            wait_time = time.time() - wait_start

            # 统计
            self._stats["connections_borrowed"] += 1
            self._stats["wait_time_total"] += wait_time
            self._stats["wait_count"] += 1

            if wait_time > 0.1:  # 超过 100ms 记录日志
                logger.warning(f"获取连接等待时间过长: {wait_time:.3f}s")

            yield conn

        except queue.Empty:
            logger.error(f"连接池耗尽，等待超时 {self.timeout}s")
            raise RuntimeError("数据库连接池耗尽")

        finally:
            # 归还连接
            if conn is not None:
                try:
                    self._pool.put(conn, timeout=0.1)
                    self._stats["connections_returned"] += 1
                except queue.Full:
                    # 池已满，关闭连接
                    logger.warning("连接池已满，关闭连接")
                    try:
                        conn.close()
                    except Exception:
                        pass

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL 语句（自动获取连接）"""
        with self.get_connection() as conn:
            return conn.execute(sql, params)

    def execute_with_retry(
        self,
        sql: str,
        params: tuple = (),
        max_retries: int = 8
    ) -> sqlite3.Cursor:
        """执行 SQL 语句（带重试）"""
        last_error = None

        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.execute(sql, params)
                    conn.commit()
                    return cursor

            except sqlite3.OperationalError as e:
                last_error = e

                # 只重试锁相关错误
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    if attempt < max_retries - 1:
                        wait = min(0.15 * (2**attempt), 2.5)
                        logger.debug(
                            f"DB 锁定，重试 {attempt + 1}/{max_retries} "
                            f"(等待 {wait*1000:.0f}ms): {sql[:50]}..."
                        )
                        time.sleep(wait)
                        continue

                raise

        raise last_error

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """查询单条记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list:
        """查询多条记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def close_all(self):
        """关闭所有连接"""
        logger.info("关闭所有数据库连接...")

        closed = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get(timeout=0.1)

                # 尝试 checkpoint
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass

                conn.close()
                closed += 1

            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"关闭连接失败: {e}")

        logger.info(f"已关闭 {closed} 个数据库连接")

    def get_stats(self) -> dict:
        """获取连接池统计信息"""
        pool_size = 0
        try:
            pool_size = self._pool.qsize()
        except Exception:
            pass

        avg_wait = 0.0
        if self._stats["wait_count"] > 0:
            avg_wait = self._stats["wait_time_total"] / self._stats["wait_count"]

        return {
            "pool_size": self.pool_size,
            "available_connections": pool_size,
            "total_created": self._stats["connections_created"],
            "total_borrowed": self._stats["connections_borrowed"],
            "total_returned": self._stats["connections_returned"],
            "avg_wait_time_ms": avg_wait * 1000,
        }

    def health_check(self) -> bool:
        """健康检查"""
        try:
            with self.get_connection() as conn:
                result = conn.execute("SELECT 1").fetchone()
                return result[0] == 1
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return False


# 全局连接池实例（单例模式）
_connection_pools: dict = {}
_pools_lock = threading.Lock()


def get_connection_pool(
    db_path: str = None,
    pool_size: int = None,
    force_new: bool = False
) -> SQLiteConnectionPool:
    """获取全局连接池实例

    Args:
        db_path: 数据库路径（默认使用项目路径）
        pool_size: 连接池大小
        force_new: 强制创建新实例（用于测试）

    Returns:
        SQLiteConnectionPool 实例
    """
    if db_path is None:
        from application.paths import get_db_path
        db_path = get_db_path()

    with _pools_lock:
        if db_path not in _connection_pools or force_new:
            pool = SQLiteConnectionPool(db_path, pool_size=pool_size)
            pool.initialize()
            _connection_pools[db_path] = pool

        return _connection_pools[db_path]
