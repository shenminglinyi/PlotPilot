"""流式消息总线 v4 - 支持停止信号

核心设计：
1. 只使用 mp.Queue 进行跨进程通信（不再使用本地 buffer，因为那在跨进程时无效）
2. 守护进程 publish() -> mp.Queue -> SSE 接口 get_chunks_batch()
3. 停止信号也通过 mp.Queue 传递（type="stop_signal"），守护进程消费后设置本地 threading.Event
4. 简单、可靠、单队列多消息类型

Windows 兼容性：
- mp.Queue 可以安全地 pickle 序列化并传递给子进程
- 单一数据通道，避免本地缓冲与队列不同步
"""
import multiprocessing as mp
import os
import threading
import time
import logging
from queue import Full, Empty
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 默认关闭逐块 DEBUG（开发时 ROOT=DEBUG 会刷爆控制台）；开启: PLOTPILOT_VERBOSE_STREAMING=1
_VERBOSE_STREAMING_chunks = os.environ.get("PLOTPILOT_VERBOSE_STREAMING", "").lower() in (
    "1",
    "true",
    "yes",
)

# 全局队列（跨进程安全）
_stream_queue: Optional[mp.Queue] = None
_lock = threading.Lock()
_initialized = False

# 消息格式：
#   普通 chunk: {"novel_id": str, "chunk": str, "timestamp": float}
#   停止信号:   {"novel_id": str, "type": "stop_signal", "timestamp": float}
MAX_QUEUE_SIZE = 10000


def init_streaming_bus() -> mp.Queue:
    """初始化流式队列（主进程调用）

    返回可 pickle 序列化的 mp.Queue，用于跨进程通信。
    """
    global _stream_queue, _initialized

    if _initialized and _stream_queue is not None:
        return _stream_queue

    with _lock:
        if _initialized and _stream_queue is not None:
            return _stream_queue

        logger.info("[StreamingBus] 初始化跨进程队列...")
        _stream_queue = mp.Queue(maxsize=MAX_QUEUE_SIZE)
        _initialized = True
        logger.info("[StreamingBus] 队列初始化完成，maxsize=%d", MAX_QUEUE_SIZE)

    return _stream_queue


def inject_stream_queue(queue: mp.Queue):
    """子进程注入队列"""
    global _stream_queue
    _stream_queue = queue
    logger.info("[StreamingBus] 子进程已注入队列")


def get_stream_queue() -> Optional[mp.Queue]:
    """获取流式队列"""
    return _stream_queue


class StreamingBus:
    """流式消息总线 v4 - 纯队列模式 + 停止信号

    架构：
    - 守护进程 -> publish() -> mp.Queue -> SSE 接口 -> get_chunks_batch()
    - 主进程 -> publish_stop_signal() -> mp.Queue -> 守护进程 -> consume_stop_signals()
    - 不再使用本地 buffer（跨进程无效）
    - 简单、可靠、单队列多消息类型
    """

    MAX_BATCH_CHUNKS = 200

    def __init__(self, queue: Optional[mp.Queue] = None):
        if queue is not None:
            inject_stream_queue(queue)

    def publish(self, novel_id: str, chunk: str, metadata: Optional[Dict] = None):
        """发布增量文字（守护进程调用）

        重要：单书长章节流式时，队列内按时间顺序排队；**不得**在「背压」时从队头批量
        discard，否则丢掉的是**正文开头**的 chunk，前端会出现句首残缺（如以「的」起句）。

        队列满时：只放弃**当前这一条**增量并打日志，避免为写入新消息而清空队头。
        """
        if not chunk:
            return

        queue = get_stream_queue()
        if queue is None:
            return

        message = {
            "novel_id": novel_id,
            "chunk": chunk,
            "timestamp": time.time(),
        }

        try:
            queue.put_nowait(message)
            if _VERBOSE_STREAMING_chunks:
                logger.debug("[StreamingBus] publish: %s, %d chars", novel_id, len(chunk))
        except Full:
            # 不再 get_nowait 清空队头：队头几乎一定是本章较早的正文，丢掉会导致开篇缺失。
            try:
                qsize = queue.qsize()
            except Exception:
                qsize = -1
            logger.warning(
                "[StreamingBus] 队列满，丢弃本条 chunk（约 %d 字）novel=%s qsize≈%s；"
                "请检查 SSE 消费是否阻塞或增大 MAX_QUEUE_SIZE",
                len(chunk),
                novel_id,
                qsize,
            )
        except Exception as e:
            logger.error("[StreamingBus] 发布消息失败: %s", e)

    def publish_audit_event(self, novel_id: str, event_type: str, data: Optional[Dict] = None):
        """发布审计事件（守护进程调用）

        用于流式推送审计进度，让前端实时看到审计状态。

        Args:
            novel_id: 小说 ID
            event_type: 事件类型
                - "audit_start": 审计开始
                - "audit_voice_check": 文风预检
                - "audit_voice_result": 文风预检结果
                - "audit_aftermath": 章后管线
                - "audit_tension": 张力打分
                - "audit_tension_result": 张力打分结果
                - "audit_complete": 审计完成
            data: 事件数据
        """
        queue = get_stream_queue()
        if queue is None:
            return

        message = {
            "novel_id": novel_id,
            "type": "audit_event",
            "event_type": event_type,
            "data": data or {},
            "timestamp": time.time(),
        }

        try:
            queue.put_nowait(message)
            if _VERBOSE_STREAMING_chunks:
                logger.debug("[StreamingBus] publish_audit_event: %s, %s", novel_id, event_type)
        except Full:
            # 队列满时丢弃旧消息
            for _ in range(10):
                try:
                    queue.get_nowait()
                except Empty:
                    break
            try:
                queue.put_nowait(message)
            except Full:
                pass

    def publish_stop_signal(self, novel_id: str):
        """发布停止信号消息（主进程 /stop API 调用）

        守护进程消费到后调用 novel_stop_signal.set_local_novel_stop()。
        消息格式与普通 chunk 不同，通过 type 字段区分。
        """
        queue = get_stream_queue()
        if queue is None:
            logger.warning("[StreamingBus] 队列未初始化，无法发布停止信号")
            return

        message = {
            "novel_id": novel_id,
            "type": "stop_signal",
            "timestamp": time.time(),
        }

        try:
            queue.put_nowait(message)
            logger.info("[StreamingBus] 停止信号已发布: %s", novel_id)
        except Full:
            # 队列满时强制丢弃旧消息，确保停止信号能送达
            dropped = 0
            for _ in range(100):
                try:
                    queue.get_nowait()
                    dropped += 1
                except Empty:
                    break
            try:
                queue.put_nowait(message)
                logger.warning(
                    "[StreamingBus] 队列满，丢弃 %d 条旧消息后发布停止信号: %s",
                    dropped, novel_id
                )
            except Full:
                logger.warning("[StreamingBus] 队列仍满，停止信号丢弃: %s", novel_id)
        except Exception as e:
            logger.error("[StreamingBus] 发布停止信号失败: %s", e)

    def publish_start_signal(self, novel_id: str):
        """发布启动信号消息（主进程 /start API 调用）

        守护进程消费到后调用 novel_stop_signal.clear_local_novel_stop()，
        清除本地 threading.Event 以便小说可以重新启动。
        """
        queue = get_stream_queue()
        if queue is None:
            return

        message = {
            "novel_id": novel_id,
            "type": "start_signal",
            "timestamp": time.time(),
        }

        try:
            queue.put_nowait(message)
            logger.info("[StreamingBus] 启动信号已发布: %s", novel_id)
        except Full:
            # 丢弃旧消息腾出空间
            for _ in range(50):
                try:
                    queue.get_nowait()
                except Empty:
                    break
            try:
                queue.put_nowait(message)
            except Full:
                pass

    def consume_control_signals(self, novel_id: str = None) -> List[str]:
        """消费队列中的控制信号消息（停止/启动），设置/清除本地 threading.Event。

        此方法由守护进程的主循环调用。
        返回收到信号的小说 ID 列表。

        Args:
            novel_id: 可选，只消费指定小说的信号；None 则消费所有
        """
        from application.engine.services.novel_stop_signal import (
            set_local_novel_stop,
            clear_local_novel_stop,
        )

        affected_novels: List[str] = []
        other_messages: List[Dict] = []

        queue = get_stream_queue()
        if queue is None:
            return affected_novels

        # 只消费少量消息，避免阻塞正常 chunk 消费
        for _ in range(50):
            try:
                message = queue.get_nowait()
                if not isinstance(message, dict):
                    continue

                msg_type = message.get("type")
                msg_novel_id = message.get("novel_id")

                if msg_type == "stop_signal":
                    if novel_id is None or msg_novel_id == novel_id:
                        set_local_novel_stop(msg_novel_id)
                        affected_novels.append(msg_novel_id)
                    else:
                        other_messages.append(message)
                elif msg_type == "start_signal":
                    if novel_id is None or msg_novel_id == novel_id:
                        clear_local_novel_stop(msg_novel_id)
                        affected_novels.append(msg_novel_id)
                    else:
                        other_messages.append(message)
                else:
                    # 非控制信号消息，放回队列（留给 get_chunks_batch 消费）
                    other_messages.append(message)
            except Empty:
                break
            except Exception as e:
                logger.debug("[StreamingBus] 消费控制信号异常: %s", e)
                break

        # 放回非目标消息
        for msg in other_messages:
            try:
                queue.put_nowait(msg)
            except Full:
                pass

        return affected_novels

    # 保留旧方法名作为别名（向后兼容）
    def consume_stop_signals(self, novel_id: str = None) -> List[str]:
        """consume_control_signals 的别名（向后兼容）"""
        return self.consume_control_signals(novel_id)

    def get_chunks_batch(self, novel_id: str, max_chunks: int = None) -> List[str]:
        """批量获取指定小说的所有待推送 chunks（SSE 接口调用）

        同时消费停止信号消息并设置本地 threading.Event。

        Args:
            novel_id: 小说 ID
            max_chunks: 最大获取数量

        Returns:
            chunk 字符串列表
        """
        max_chunks = max_chunks or self.MAX_BATCH_CHUNKS
        chunks: List[str] = []
        other_messages: List[Dict] = []

        queue = get_stream_queue()
        if queue is None:
            return chunks

        # 读取队列中的消息
        for _ in range(max_chunks):
            try:
                message = queue.get_nowait()
                if isinstance(message, dict):
                    msg_type = message.get("type")
                    msg_novel_id = message.get("novel_id")
                    msg_chunk = message.get("chunk")

                    # 停止信号：设置本地 Event
                    if msg_type == "stop_signal":
                        try:
                            from application.engine.services.novel_stop_signal import set_local_novel_stop
                            set_local_novel_stop(msg_novel_id)
                            logger.info("[StreamingBus] get_chunks_batch: 消费到停止信号: %s", msg_novel_id)
                        except Exception:
                            pass
                        continue

                    # 启动信号：清除本地 Event
                    if msg_type == "start_signal":
                        try:
                            from application.engine.services.novel_stop_signal import clear_local_novel_stop
                            clear_local_novel_stop(msg_novel_id)
                            logger.info("[StreamingBus] get_chunks_batch: 消费到启动信号: %s", msg_novel_id)
                        except Exception:
                            pass
                        continue

                    # 普通 chunk 消息
                    if msg_novel_id == novel_id and msg_chunk:
                        chunks.append(msg_chunk)
                    elif msg_novel_id != novel_id:
                        # 收集其他小说的消息，稍后放回
                        other_messages.append(message)
            except Empty:
                break
            except Exception as e:
                if _VERBOSE_STREAMING_chunks:
                    logger.debug("[StreamingBus] 队列读取异常: %s", e)
                break

        # 放回其他小说的消息（一次性批量放回）
        if other_messages:
            for msg in other_messages:
                try:
                    queue.put_nowait(msg)
                except Full:
                    # 队列满时丢弃
                    pass

        if chunks and _VERBOSE_STREAMING_chunks:
            logger.debug(
                "[StreamingBus] get_chunks_batch: %s, %d chunks",
                novel_id, len(chunks)
            )

        return chunks

    def get_chunks_and_events_batch(self, novel_id: str, max_chunks: int = None) -> Dict[str, Any]:
        """批量获取指定小说的 chunks 和审计事件（SSE 接口调用）

        Args:
            novel_id: 小说 ID
            max_chunks: 最大获取数量

        Returns:
            {
                "chunks": List[str],  # 增量文字
                "audit_events": List[Dict],  # 审计事件
            }
        """
        max_chunks = max_chunks or self.MAX_BATCH_CHUNKS
        chunks: List[str] = []
        audit_events: List[Dict] = []
        other_messages: List[Dict] = []

        queue = get_stream_queue()
        if queue is None:
            return {"chunks": chunks, "audit_events": audit_events}

        # 读取队列中的消息
        for _ in range(max_chunks):
            try:
                message = queue.get_nowait()
                if isinstance(message, dict):
                    msg_type = message.get("type")
                    msg_novel_id = message.get("novel_id")
                    msg_chunk = message.get("chunk")

                    # 停止信号：设置本地 Event
                    if msg_type == "stop_signal":
                        try:
                            from application.engine.services.novel_stop_signal import set_local_novel_stop
                            set_local_novel_stop(msg_novel_id)
                            logger.info("[StreamingBus] get_chunks_and_events_batch: 消费到停止信号: %s", msg_novel_id)
                        except Exception:
                            pass
                        continue

                    # 启动信号：清除本地 Event
                    if msg_type == "start_signal":
                        try:
                            from application.engine.services.novel_stop_signal import clear_local_novel_stop
                            clear_local_novel_stop(msg_novel_id)
                            logger.info("[StreamingBus] get_chunks_and_events_batch: 消费到启动信号: %s", msg_novel_id)
                        except Exception:
                            pass
                        continue

                    # 审计事件
                    if msg_type == "audit_event":
                        if msg_novel_id == novel_id:
                            audit_events.append({
                                "event_type": message.get("event_type"),
                                "data": message.get("data", {}),
                                "timestamp": message.get("timestamp"),
                            })
                        else:
                            other_messages.append(message)
                        continue

                    # 普通 chunk 消息
                    if msg_novel_id == novel_id and msg_chunk:
                        chunks.append(msg_chunk)
                    elif msg_novel_id != novel_id:
                        # 收集其他小说的消息，稍后放回
                        other_messages.append(message)
            except Empty:
                break
            except Exception as e:
                if _VERBOSE_STREAMING_chunks:
                    logger.debug("[StreamingBus] 队列读取异常: %s", e)
                break

        # 放回其他小说的消息（一次性批量放回）
        if other_messages:
            for msg in other_messages:
                try:
                    queue.put_nowait(msg)
                except Full:
                    # 队列满时丢弃
                    pass

        return {"chunks": chunks, "audit_events": audit_events}

    def get_chunk(self, novel_id: str, timeout: float = 0.05) -> Optional[str]:
        """获取单个 chunk（兼容旧接口）"""
        chunks = self.get_chunks_batch(novel_id, max_chunks=1)
        return chunks[0] if chunks else None

    async def get_chunk_async(self, novel_id: str, timeout: float = 0.05) -> Optional[str]:
        """异步获取单个 chunk"""
        return self.get_chunk(novel_id, timeout)

    def clear(self, novel_id: str):
        """清理指定小说的缓冲（目前无本地缓冲，此方法为空操作）"""
        # 清空队列中该小说的消息
        queue = get_stream_queue()
        if queue is None:
            return

        other_messages: List[Dict] = []
        cleared = 0

        for _ in range(1000):
            try:
                message = queue.get_nowait()
                if isinstance(message, dict):
                    if message.get("novel_id") != novel_id:
                        other_messages.append(message)
                    else:
                        cleared += 1
            except Empty:
                break

        # 放回其他小说的消息
        for msg in other_messages:
            try:
                queue.put_nowait(msg)
            except Full:
                pass

        if cleared > 0 and _VERBOSE_STREAMING_chunks:
            logger.debug("[StreamingBus] clear: %s, 清除 %d 条消息", novel_id, cleared)

    def get_queue_size(self) -> int:
        """获取队列当前大小"""
        queue = get_stream_queue()
        if queue is None:
            return 0
        try:
            # 注意：qsize() 在某些平台上可能不准确
            return queue.qsize()
        except Exception:
            return 0

    def update_beat(self, novel_id: str, beat_index: int, word_count: int):
        """更新节拍进度（兼容旧接口，当前为空操作）

        注意：v3 版本不再维护本地元数据状态，此方法仅为兼容性保留。
        节拍进度通过 novel.current_beat_index 在数据库中维护。
        """
        if _VERBOSE_STREAMING_chunks:
            logger.debug(
                "[StreamingBus] update_beat: %s, beat=%d, words=%d (no-op)",
                novel_id, beat_index, word_count,
            )

    def get_metadata(self, novel_id: str) -> Dict[str, Any]:
        """获取流元数据（兼容旧接口）"""
        return {}

    def reset_chapter(self, novel_id: str, chapter_number: int):
        """章节开始时重置状态（兼容旧接口）"""
        self.clear(novel_id)
        logger.info("[StreamingBus] reset_chapter: %s, chapter=%d", novel_id, chapter_number)


# 全局实例
streaming_bus = StreamingBus()
