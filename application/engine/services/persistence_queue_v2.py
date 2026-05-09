"""持久化队列 V2 - 基于 SQLite 的可靠队列

核心改进：
1. 数据持久化：进程崩溃不丢失数据
2. 自动重试：失败任务自动重试
3. 优先级队列：支持优先级调度
4. 清理机制：自动清理旧任务

架构优势：
- 单一写入者模式：避免并发冲突
- WAL 模式：读写不阻塞
- 事务保证：ACID 特性
"""
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class PersistenceCommandType(Enum):
    """持久化命令类型"""
    # 章节相关
    UPSERT_CHAPTER = "upsert_chapter"
    UPDATE_CHAPTER_STATUS = "update_chapter_status"
    UPDATE_CHAPTER_TENSION = "update_chapter_tension"
    UPDATE_CHAPTER_WORD_COUNT = "update_chapter_word_count"

    # 小说相关
    PATCH_NOVEL = "patch_novel"
    SAVE_NOVEL = "save_novel"
    UPDATE_NOVEL_STATE = "update_novel_state"

    # 知识库相关
    UPSERT_KNOWLEDGE = "upsert_knowledge"

    # 故事节点相关
    SAVE_STORY_NODE = "save_story_node"

    # 伏笔
    UPDATE_FORESHADOWS = "update_foreshadows"

    # 故事线
    UPDATE_STORYLINES = "update_storylines"

    # 剧情弧光
    UPDATE_PLOT_ARC = "update_plot_arc"

    # 编年史
    UPDATE_CHRONICLES = "update_chronicles"

    # 叙事知识
    UPDATE_KNOWLEDGE = "update_knowledge"

    # Bible
    UPDATE_BIBLE = "update_bible"

    # 三元组
    UPDATE_TRIPLES = "update_triples"

    # 快照
    UPDATE_SNAPSHOTS = "update_snapshots"

    # 批量命令
    BATCH = "batch"


@dataclass
class PersistenceCommand:
    """持久化命令"""
    command_type: str
    payload: Dict[str, Any]
    priority: int = 0
    max_retries: int = 3
    command_id: Optional[int] = None
    status: str = "pending"
    retry_count: int = 0
    created_at: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "PersistenceCommand":
        return cls(
            command_id=row["id"],
            command_type=row["command_type"],
            payload=json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"],
            priority=row.get("priority", 0),
            max_retries=row.get("max_retries", 3),
            status=row["status"],
            retry_count=row.get("retry_count", 0),
            created_at=row.get("created_at"),
            error_message=row.get("error_message"),
        )


class PersistentQueueV2:
    """基于 SQLite 的持久化队列"""

    # 批量处理大小
    BATCH_SIZE = 10

    # 清理阈值
    CLEANUP_THRESHOLD = 1000

    def __init__(self, db_pool):
        """初始化持久化队列

        Args:
            db_pool: SQLiteConnectionPool 实例
        """
        self._db_pool = db_pool
        self._consumer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._handlers: Dict[str, Callable] = {}
        self._stats = {
            "queued": 0,
            "processed": 0,
            "failed": 0,
            "retried": 0,
        }

        # 确保队列表存在
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """确保队列表存在"""
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS persistence_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        command_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        priority INTEGER DEFAULT 0,
                        retry_count INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 3,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        error_message TEXT
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_persistence_queue_status_created "
                    "ON persistence_queue(status, created_at)"
                )
                conn.commit()
                logger.debug("持久化队列表已确保存在")
        except Exception as e:
            logger.error(f"创建持久化队列表失败: {e}")
            raise

    def push(
        self,
        command_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        max_retries: int = 3
    ) -> int:
        """推入持久化命令

        Args:
            command_type: 命令类型
            payload: 命令负载
            priority: 优先级（数字越大优先级越高）
            max_retries: 最大重试次数

        Returns:
            命令 ID
        """
        try:
            with self._db_pool.get_connection() as conn:
                cursor = conn.execute(
                    """INSERT INTO persistence_queue
                       (command_type, payload, priority, max_retries)
                       VALUES (?, ?, ?, ?)""",
                    (command_type, json.dumps(payload), priority, max_retries)
                )
                conn.commit()

                command_id = cursor.lastrowid
                self._stats["queued"] += 1

                logger.debug(f"命令已入队: id={command_id}, type={command_type}")
                return command_id

        except Exception as e:
            logger.error(f"推入命令失败: {command_type}, {e}")
            raise

    def push_batch(self, commands: List[tuple]) -> List[int]:
        """批量推入命令

        Args:
            commands: [(command_type, payload), ...]

        Returns:
            命令 ID 列表
        """
        if not commands:
            return []

        try:
            command_ids = []
            with self._db_pool.get_connection() as conn:
                for command_type, payload in commands:
                    cursor = conn.execute(
                        """INSERT INTO persistence_queue
                           (command_type, payload)
                           VALUES (?, ?)""",
                        (command_type, json.dumps(payload))
                    )
                    command_ids.append(cursor.lastrowid)

                conn.commit()
                self._stats["queued"] += len(commands)

                logger.debug(f"批量入队 {len(commands)} 个命令")
                return command_ids

        except Exception as e:
            logger.error(f"批量推入命令失败: {e}")
            raise

    def pop(self, batch_size: int = None) -> List[PersistenceCommand]:
        """弹出待处理命令（FIFO + 优先级）

        Args:
            batch_size: 批量大小

        Returns:
            命令列表
        """
        batch_size = batch_size or self.BATCH_SIZE

        try:
            with self._db_pool.get_connection() as conn:
                # 原子操作：查询 + 更新状态
                rows = conn.execute(
                    """UPDATE persistence_queue
                       SET status = 'processing', started_at = CURRENT_TIMESTAMP
                       WHERE id IN (
                           SELECT id FROM persistence_queue
                           WHERE status = 'pending'
                           ORDER BY priority DESC, created_at
                           LIMIT ?
                       )
                       RETURNING *""",
                    (batch_size,)
                ).fetchall()

                conn.commit()

                commands = [PersistenceCommand.from_row(dict(row)) for row in rows]
                return commands

        except Exception as e:
            logger.error(f"弹出命令失败: {e}")
            return []

    def ack(self, command_id: int):
        """确认处理成功"""
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """UPDATE persistence_queue
                       SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (command_id,)
                )
                conn.commit()
                self._stats["processed"] += 1

        except Exception as e:
            logger.error(f"确认命令失败: id={command_id}, {e}")

    def nack(self, command_id: int, error: str, retry: bool = True):
        """处理失败

        Args:
            command_id: 命令 ID
            error: 错误信息
            retry: 是否重试
        """
        try:
            with self._db_pool.get_connection() as conn:
                # 查询当前重试次数
                row = conn.execute(
                    "SELECT retry_count, max_retries FROM persistence_queue WHERE id = ?",
                    (command_id,)
                ).fetchone()

                if not row:
                    logger.error(f"命令不存在: id={command_id}")
                    return

                retry_count = row["retry_count"]
                max_retries = row["max_retries"]

                if retry and retry_count < max_retries:
                    # 重试
                    conn.execute(
                        """UPDATE persistence_queue
                           SET status = 'pending',
                               retry_count = retry_count + 1,
                               error_message = ?
                           WHERE id = ?""",
                        (error, command_id)
                    )
                    self._stats["retried"] += 1
                    logger.warning(
                        f"命令将重试: id={command_id}, "
                        f"attempt={retry_count + 1}/{max_retries}, error={error}"
                    )
                else:
                    # 标记失败
                    conn.execute(
                        """UPDATE persistence_queue
                           SET status = 'failed',
                               completed_at = CURRENT_TIMESTAMP,
                               error_message = ?
                           WHERE id = ?""",
                        (error, command_id)
                    )
                    self._stats["failed"] += 1
                    logger.error(
                        f"命令最终失败: id={command_id}, "
                        f"attempts={retry_count}/{max_retries}, error={error}"
                    )

                conn.commit()

        except Exception as e:
            logger.error(f"处理失败命令异常: id={command_id}, {e}")

    def register_handler(self, command_type: str, handler: Callable):
        """注册命令处理器"""
        self._handlers[command_type] = handler
        logger.debug(f"已注册处理器: {command_type}")

    def start_consumer(self):
        """启动消费者线程"""
        if self._consumer_thread and self._consumer_thread.is_alive():
            logger.warning("消费者线程已在运行")
            return

        self._stop_event.clear()
        self._consumer_thread = threading.Thread(
            target=self._consume_loop,
            name="PersistenceQueueConsumer",
            daemon=True,
        )
        self._consumer_thread.start()
        logger.info("✅ 持久化队列消费者已启动")

    def stop_consumer(self):
        """停止消费者线程"""
        self._stop_event.set()
        if self._consumer_thread:
            self._consumer_thread.join(timeout=5)
        logger.info("🛑 持久化队列消费者已停止")

    def _consume_loop(self):
        """消费者主循环"""
        logger.info("持久化队列消费者开始轮询...")

        while not self._stop_event.is_set():
            try:
                # 弹出一批命令
                commands = self.pop()

                if not commands:
                    # 队列为空，休眠 0.5 秒
                    time.sleep(0.5)
                    continue

                # 处理每个命令
                for command in commands:
                    if self._stop_event.is_set():
                        break

                    self._process_command(command)

                # 定期清理
                if self._stats["processed"] % 100 == 0:
                    self._cleanup_old_tasks()

            except Exception as e:
                logger.error(f"消费者异常: {e}", exc_info=True)
                time.sleep(1)

        logger.info("持久化队列消费者已退出")

    def _process_command(self, command: PersistenceCommand):
        """处理单个命令"""
        handler = self._handlers.get(command.command_type)

        if not handler:
            logger.warning(f"未注册的命令类型: {command.command_type}")
            self.nack(command.command_id, f"未注册的命令类型: {command.command_type}", retry=False)
            return

        try:
            handler(command.payload)
            self.ack(command.command_id)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"处理命令失败: {command.command_type}, {error_msg}")
            self.nack(command.command_id, error_msg, retry=True)

    def _cleanup_old_tasks(self):
        """清理旧任务（7天前）"""
        try:
            with self._db_pool.get_connection() as conn:
                result = conn.execute(
                    """DELETE FROM persistence_queue
                       WHERE status IN ('completed', 'failed')
                       AND completed_at < datetime('now', '-7 days')"""
                )
                conn.commit()

                if result.rowcount > 0:
                    logger.info(f"已清理 {result.rowcount} 个旧任务")

        except Exception as e:
            logger.error(f"清理旧任务失败: {e}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        try:
            with self._db_pool.get_connection() as conn:
                row = conn.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                    FROM persistence_queue"""
                ).fetchone()

                return {
                    "queue_stats": dict(row),
                    "consumer_stats": self._stats,
                    "consumer_running": self._consumer_thread.is_alive() if self._consumer_thread else False,
                }

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"error": str(e)}


# 全局实例（需要在启动时初始化）
_persistent_queue_v2: Optional[PersistentQueueV2] = None


def get_persistent_queue_v2() -> PersistentQueueV2:
    """获取全局持久化队列实例"""
    global _persistent_queue_v2
    if _persistent_queue_v2 is None:
        raise RuntimeError("持久化队列未初始化，请先调用 initialize_persistent_queue_v2()")
    return _persistent_queue_v2


def initialize_persistent_queue_v2(db_pool) -> PersistentQueueV2:
    """初始化持久化队列"""
    global _persistent_queue_v2
    _persistent_queue_v2 = PersistentQueueV2(db_pool)
    logger.info("✅ 持久化队列 V2 已初始化")
    return _persistent_queue_v2
