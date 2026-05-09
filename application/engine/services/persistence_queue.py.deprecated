"""持久化队列 - 单一写入者模式（CQRS / Actor Model）

核心设计：
1. 守护进程不直接写 DB，而是将持久化命令推入队列
2. API 进程启动专用线程消费队列，作为唯一的 DB 写入者
3. 彻底消除 SQLite 多进程锁竞争

架构优势：
- 隔离性：守护进程崩溃不影响 API 响应
- 一致性：所有写操作序列化，无锁竞争
- 数据安全：队列中的命令在内存中排队，亚秒级落盘
"""
import json
import logging
import multiprocessing as mp
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
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
    timestamp: float
    command_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "PersistenceCommand":
        return cls(**data)


class PersistenceQueue:
    """持久化队列 - 跨进程安全"""

    def __init__(self):
        self._queue: Optional[mp.Queue] = None
        self._consumer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._handlers: Dict[str, Callable] = {}
        self._stats = {"queued": 0, "processed": 0, "failed": 0}

    def initialize(self) -> mp.Queue:
        """初始化队列（在主进程调用）"""
        if self._queue is None:
            self._queue = mp.Queue()
            logger.info("✅ 持久化队列已初始化")
        return self._queue

    def get_queue(self) -> Optional[mp.Queue]:
        """获取队列实例"""
        return self._queue

    def inject_queue(self, queue: mp.Queue) -> None:
        """注入队列（守护进程启动时调用）"""
        self._queue = queue
        logger.info("✅ 持久化队列已注入")

    def register_handler(self, command_type: str, handler: Callable) -> None:
        """注册命令处理器"""
        self._handlers[command_type] = handler

    def push(self, command_type: str, payload: Dict[str, Any]) -> bool:
        """推入持久化命令（守护进程调用）"""
        if self._queue is None:
            logger.warning(f"持久化队列未初始化，丢弃命令: {command_type}")
            return False

        try:
            command = PersistenceCommand(
                command_type=command_type,
                payload=payload,
                timestamp=time.time(),
            )
            self._queue.put(command.to_dict(), block=False)
            self._stats["queued"] += 1
            return True
        except Exception as e:
            logger.error(f"推入持久化队列失败: {e}")
            return False

    def push_batch(self, commands: List[tuple]) -> bool:
        """批量推入命令"""
        if not commands:
            return True

        batch_payload = [
            {"command_type": ct, "payload": p}
            for ct, p in commands
        ]
        return self.push(PersistenceCommandType.BATCH.value, {"commands": batch_payload})

    def start_consumer(self) -> None:
        """启动消费者线程（API 进程调用）"""
        if self._consumer_thread is not None and self._consumer_thread.is_alive():
            logger.warning("持久化消费者线程已在运行")
            return

        self._stop_event.clear()
        self._consumer_thread = threading.Thread(
            target=self._consume_loop,
            name="PersistenceConsumer",
            daemon=True,
        )
        self._consumer_thread.start()
        logger.info("✅ 持久化消费者线程已启动")

    def stop_consumer(self) -> None:
        """停止消费者线程"""
        self._stop_event.set()
        if self._consumer_thread:
            self._consumer_thread.join(timeout=5)
        logger.info("🛑 持久化消费者线程已停止")

    def _consume_loop(self) -> None:
        """消费者主循环（运行在 API 进程）"""
        logger.info("持久化消费者开始轮询...")

        while not self._stop_event.is_set():
            try:
                # 阻塞获取，超时 0.5 秒
                try:
                    item = self._queue.get(block=True, timeout=0.5)
                except queue.Empty:
                    continue

                self._process_command(item)

            except Exception as e:
                logger.error(f"持久化消费者异常: {e}", exc_info=True)

        # 处理剩余命令
        self._drain_queue()

    def _process_command(self, item: Dict) -> None:
        """处理单个命令"""
        command_type = item.get("command_type")
        payload = item.get("payload", {})

        try:
            if command_type == PersistenceCommandType.BATCH.value:
                # 批量命令
                commands = payload.get("commands", [])
                for cmd in commands:
                    self._process_single_command(
                        cmd.get("command_type"),
                        cmd.get("payload", {})
                    )
            else:
                self._process_single_command(command_type, payload)

            self._stats["processed"] += 1

        except Exception as e:
            logger.error(f"处理持久化命令失败: {command_type}, {e}")
            self._stats["failed"] += 1

    def _process_single_command(self, command_type: str, payload: Dict) -> None:
        """处理单个命令（DB 被锁时重试，最多 3 次退避）"""
        handler = self._handlers.get(command_type)
        if not handler:
            logger.warning(f"未注册的命令类型: {command_type}")
            return

        max_retries = 3
        for attempt in range(max_retries):
            try:
                handler(payload)
                return  # 成功，直接返回
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    if attempt < max_retries - 1:
                        wait = 0.3 * (attempt + 1)
                        logger.warning(
                            "DB 被锁，重试 %d/%d (等待%.1fs): %s",
                            attempt + 1, max_retries, wait, command_type,
                        )
                        time.sleep(wait)
                        continue
                    else:
                        logger.error(
                            "DB 被锁，重试耗尽，丢弃命令: %s", command_type
                        )
                else:
                    raise
            except Exception as e:
                # 非 DB 锁错误，不重试
                raise

    def _drain_queue(self) -> None:
        """排空队列（带超时保护，避免 DB 被锁时无限等待）"""
        drained = 0
        deadline = time.monotonic() + 3.0  # 最多排空 3 秒
        while time.monotonic() < deadline:
            try:
                item = self._queue.get(block=False)
                self._process_command(item)
                drained += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"排空队列时处理命令失败: {e}")
                break
        if drained > 0:
            logger.info(f"队列已排空，处理了 {drained} 条命令")
        if time.monotonic() >= deadline:
            logger.warning("排空队列超时（3s），可能还有未处理命令")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        queue_size = 0
        if self._queue:
            try:
                # 尝试获取队列大小（不保证准确）
                queue_size = self._queue.qsize()
            except Exception:
                pass

        return {
            **self._stats,
            "queue_size": queue_size,
        }


# 全局单例
_persistence_queue: Optional[PersistenceQueue] = None


def get_persistence_queue() -> PersistenceQueue:
    """获取全局持久化队列实例"""
    global _persistence_queue
    if _persistence_queue is None:
        _persistence_queue = PersistenceQueue()
    return _persistence_queue


def initialize_persistence_queue() -> mp.Queue:
    """初始化持久化队列（主进程启动时调用）"""
    pq = get_persistence_queue()
    return pq.initialize()


def inject_persistence_queue(queue: mp.Queue) -> None:
    """注入持久化队列（守护进程启动时调用）"""
    pq = get_persistence_queue()
    pq.inject_queue(queue)


def register_persistence_handlers() -> None:
    """注册所有持久化处理器（主进程启动时调用）"""
    pq = get_persistence_queue()

    # 章节相关处理器
    def handle_upsert_chapter(payload: Dict) -> None:
        """处理章节内容更新"""
        try:
            from domain.novel.value_objects.novel_id import NovelId
            from domain.novel.entities.chapter import Chapter, ChapterStatus
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            novel_id = payload.get("novel_id")
            chapter_number = payload.get("chapter_number")
            content = payload.get("content", "")
            status = payload.get("status", "draft")

            # 使用轻量 SQL 更新
            db.execute(
                """INSERT INTO chapters (novel_id, number, content, status, word_count, updated_at)
                VALUES (?, ?, ?, ?, LENGTH(?), CURRENT_TIMESTAMP)
                ON CONFLICT(novel_id, number) DO UPDATE SET
                    content = excluded.content,
                    status = excluded.status,
                    word_count = excluded.word_count,
                    updated_at = CURRENT_TIMESTAMP""",
                (novel_id, chapter_number, content, status, content)
            )
            db.get_connection().commit()
            logger.debug(f"[PersistenceQueue] 章节已持久化: novel={novel_id} ch={chapter_number}")

        except Exception as e:
            logger.error(f"[PersistenceQueue] 章节持久化失败: {e}")

    def handle_update_chapter_tension(payload: Dict) -> None:
        """处理章节张力值更新"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            novel_id = payload.get("novel_id")
            chapter_number = payload.get("chapter_number")
            tension_score = payload.get("tension_score")

            db.execute(
                "UPDATE chapters SET tension_score = ?, updated_at = CURRENT_TIMESTAMP WHERE novel_id = ? AND number = ?",
                (tension_score, novel_id, chapter_number)
            )
            db.get_connection().commit()
            logger.debug(f"[PersistenceQueue] 张力值已持久化: novel={novel_id} ch={chapter_number}")

        except Exception as e:
            logger.error(f"[PersistenceQueue] 张力值持久化失败: {e}")

    def handle_patch_novel(payload: Dict) -> None:
        """处理小说增量更新"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            novel_id = payload.get("novel_id")
            fields = payload.get("fields", {})

            if not fields:
                return

            # 构建 SET 子句
            set_clauses = [f"{k} = ?" for k in fields.keys()]
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            sql = f"UPDATE novels SET {', '.join(set_clauses)} WHERE id = ?"
            db.execute(sql, list(fields.values()) + [novel_id])
            db.get_connection().commit()
            logger.debug(f"[PersistenceQueue] 小说已持久化: {novel_id}")

        except Exception as e:
            logger.error(f"[PersistenceQueue] 小说持久化失败: {e}")

    # 注册处理器
    pq.register_handler(PersistenceCommandType.UPSERT_CHAPTER.value, handle_upsert_chapter)
    pq.register_handler(PersistenceCommandType.UPDATE_CHAPTER_TENSION.value, handle_update_chapter_tension)
    pq.register_handler(PersistenceCommandType.PATCH_NOVEL.value, handle_patch_novel)

    # 新增：小说状态更新处理器
    def handle_update_novel_state(payload: Dict) -> None:
        """处理小说状态更新"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            novel_id = payload.get("novel_id")

            # 更新小说状态字段
            # 🔥 needs_review 是计算字段（由 current_stage == paused_for_review 推导），
            # novels 表无此列，不能写入 DB，否则会导致 "no such column: needs_review" 错误
            fields = {
                "autopilot_status": payload.get("autopilot_status"),
                "current_stage": payload.get("current_stage"),
                "current_act": payload.get("current_act"),
                "current_chapter_in_act": payload.get("current_chapter_in_act"),
                "current_beat_index": payload.get("current_beat_index"),
                "current_auto_chapters": payload.get("current_auto_chapters"),
                "consecutive_error_count": payload.get("consecutive_error_count"),
                "last_chapter_tension": payload.get("last_chapter_tension"),
                "auto_approve_mode": payload.get("auto_approve_mode"),
            }

            # 过滤掉 None 值
            fields = {k: v for k, v in fields.items() if v is not None}
            if not fields:
                return

            set_clauses = [f"{k} = ?" for k in fields.keys()]
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            sql = f"UPDATE novels SET {', '.join(set_clauses)} WHERE id = ?"
            db.execute(sql, list(fields.values()) + [novel_id])
            db.get_connection().commit()
            logger.debug(f"[PersistenceQueue] 小说状态已持久化: {novel_id}")

        except Exception as e:
            logger.error(f"[PersistenceQueue] 小说状态持久化失败: {e}")

    # 新增：章节状态更新处理器
    def handle_update_chapter_status(payload: Dict) -> None:
        """处理章节状态更新"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            novel_id = payload.get("novel_id")
            chapter_number = payload.get("chapter_number")
            status = payload.get("status")

            db.execute(
                "UPDATE chapters SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE novel_id = ? AND number = ?",
                (status, novel_id, chapter_number)
            )
            db.get_connection().commit()
            logger.debug(f"[PersistenceQueue] 章节状态已持久化: novel={novel_id} ch={chapter_number}")

        except Exception as e:
            logger.error(f"[PersistenceQueue] 章节状态持久化失败: {e}")

    # 新增：章节字数更新处理器
    def handle_update_chapter_word_count(payload: Dict) -> None:
        """处理章节字数更新"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            novel_id = payload.get("novel_id")
            chapter_number = payload.get("chapter_number")
            word_count = payload.get("word_count")

            db.execute(
                "UPDATE chapters SET word_count = ?, updated_at = CURRENT_TIMESTAMP WHERE novel_id = ? AND number = ?",
                (word_count, novel_id, chapter_number)
            )
            db.get_connection().commit()
            logger.debug(f"[PersistenceQueue] 章节字数已持久化: novel={novel_id} ch={chapter_number}")

        except Exception as e:
            logger.error(f"[PersistenceQueue] 章节字数持久化失败: {e}")

    # 新增：伏笔更新处理器
    def handle_update_foreshadows(payload: Dict) -> None:
        """处理伏笔更新"""
        try:
            from infrastructure.persistence.database.connection import get_database
            import json
            from datetime import datetime

            db = get_database()
            novel_id = payload.get("novel_id")
            entries = payload.get("entries", [])

            payload_json = json.dumps({"subtext_entries": entries}, ensure_ascii=False)
            now = datetime.utcnow().isoformat()

            db.execute(
                """INSERT INTO novel_foreshadow_registry (novel_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(novel_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at""",
                (novel_id, payload_json, now)
            )
            db.get_connection().commit()
            logger.debug(f"[PersistenceQueue] 伏笔已持久化: {novel_id}")

        except Exception as e:
            logger.error(f"[PersistenceQueue] 伏笔持久化失败: {e}")

    # 注册新处理器
    pq.register_handler(PersistenceCommandType.UPDATE_NOVEL_STATE.value, handle_update_novel_state)
    pq.register_handler(PersistenceCommandType.UPDATE_CHAPTER_STATUS.value, handle_update_chapter_status)
    pq.register_handler(PersistenceCommandType.UPDATE_CHAPTER_WORD_COUNT.value, handle_update_chapter_word_count)
    pq.register_handler(PersistenceCommandType.UPDATE_FORESHADOWS.value, handle_update_foreshadows)

    # 🔥 故事线更新处理器（守护进程通过持久化队列写入，避免长连接锁竞争）
    def handle_update_storylines(payload: Dict) -> None:
        """处理故事线更新"""
        try:
            from domain.novel.value_objects.novel_id import NovelId
            from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            repo = SqliteStorylineRepository(db)
            novel_id = payload.get("novel_id")
            storylines_data = payload.get("storylines", [])

            # storylines_data 是序列化后的故事线列表，逐条 save
            for sl_data in storylines_data:
                try:
                    # 尝试从 DB 获取已有故事线并更新
                    existing = repo.get_by_id(sl_data.get("id", ""))
                    if existing:
                        # 更新进度
                        if sl_data.get("progress_summary"):
                            existing.progress_summary = sl_data["progress_summary"]
                        if sl_data.get("last_active_chapter"):
                            existing.last_active_chapter = sl_data["last_active_chapter"]
                        if sl_data.get("current_milestone_index") is not None:
                            existing.current_milestone_index = sl_data["current_milestone_index"]
                        repo.save(existing)
                    else:
                        # 新建故事线（从序列化数据重建）
                        from domain.novel.entities.storyline import Storyline
                        from domain.novel.value_objects.storyline_type import StorylineType
                        from domain.novel.value_objects.storyline_status import StorylineStatus
                        sl = Storyline(
                            id=sl_data.get("id", ""),
                            novel_id=NovelId(novel_id),
                            storyline_type=StorylineType(sl_data.get("storyline_type", "main_plot")),
                            status=StorylineStatus(sl_data.get("status", "active")),
                            name=sl_data.get("name", ""),
                            description=sl_data.get("description", ""),
                            estimated_chapter_start=sl_data.get("estimated_chapter_start"),
                            estimated_chapter_end=sl_data.get("estimated_chapter_end"),
                        )
                        sl.current_milestone_index = sl_data.get("current_milestone_index", 0)
                        sl.last_active_chapter = sl_data.get("last_active_chapter", 0)
                        sl.progress_summary = sl_data.get("progress_summary", "")
                        repo.save(sl)
                except Exception as e:
                    logger.error(f"[PersistenceQueue] 故事线单条持久化失败: {e}")

            logger.debug(f"[PersistenceQueue] 故事线已持久化: novel={novel_id} count={len(storylines_data)}")
        except Exception as e:
            logger.error(f"[PersistenceQueue] 故事线持久化失败: {e}")

    pq.register_handler(PersistenceCommandType.UPDATE_STORYLINES.value, handle_update_storylines)

    logger.info("✅ 持久化处理器已注册: upsert_chapter, update_chapter_tension, patch_novel, update_novel_state, update_chapter_status, update_foreshadows, update_storylines")
