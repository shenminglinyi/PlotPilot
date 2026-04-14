"""流式消息总线 - 用于自动驾驶守护进程与 SSE 接口之间的实时通信

守护进程在独立进程中运行，SSE 接口在主进程中运行。

Windows 兼容性说明：
- Windows 使用 spawn 方式创建子进程，需要 pickle 序列化参数
- multiprocessing.Manager() 对象包含弱引用，无法被 pickle
- 解决方案：使用 multiprocessing.Queue / SimpleQueue，它们可以安全序列化传递

设计：
- 主进程创建 Queue，通过参数传递给守护进程
- 守护进程调用 publish() 写入队列
- SSE 接口调用 get_chunk() 从队列读取
"""
import asyncio
import multiprocessing as mp
import threading
import time
import logging
from collections import defaultdict
from queue import Full, Empty
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_stream_queue: Optional[mp.Queue] = None
_lock = threading.Lock()
_initialized = False
_injected_queue: Optional[mp.Queue] = None


def init_streaming_bus() -> mp.Queue:
    global _stream_queue, _initialized

    if _initialized and _stream_queue is not None:
        logger.debug("[StreamingBus] 已初始化，跳过")
        return _stream_queue

    with _lock:
        if _initialized and _stream_queue is not None:
            return _stream_queue

        logger.info("[StreamingBus] 在主进程中初始化 Queue...")
        _stream_queue = mp.Queue(maxsize=5000)
        _initialized = True
        logger.info("[StreamingBus] Queue 初始化完成")

    return _stream_queue


def inject_stream_queue(queue: mp.Queue):
    global _injected_queue
    _injected_queue = queue
    logger.info("[StreamingBus] 子进程已注入队列")


def _get_queue() -> Optional[mp.Queue]:
    global _stream_queue, _injected_queue

    if _injected_queue is not None:
        return _injected_queue

    if _stream_queue is not None:
        return _stream_queue

    current_process = mp.current_process()

    if current_process.daemon:
        logger.warning(
            "[StreamingBus] 守护进程未注入队列，流式推送不可用。"
            "请确保在启动守护进程时传入 Queue。"
        )
        return None

    logger.debug("[StreamingBus] _get_queue: 队列未初始化，尝试初始化...")
    init_streaming_bus()
    return _stream_queue


class StreamingBus:
    """流式消息总线 - 发布/订阅模式（基于 multiprocessing.Queue）

    消息格式：
        {
            "novel_id": "novel-xxx",
            "chunk": "增量文字内容"
        }
    """

    def __init__(self, queue: Optional[mp.Queue] = None):
        if queue is not None:
            inject_stream_queue(queue)

        self._subscribers: Dict[str, list] = defaultdict(list)
        self._local_positions: Dict[str, int] = defaultdict(int)

    def publish(self, novel_id: str, chunk: str):
        if not chunk:
            return

        queue = _get_queue()
        if queue is None:
            return

        try:
            message = {
                "novel_id": novel_id,
                "chunk": chunk
            }

            try:
                queue.put_nowait(message)
            except Full:
                for _ in range(100):
                    try:
                        queue.get_nowait()
                    except Empty:
                        break
                try:
                    queue.put_nowait(message)
                except Full:
                    pass

            logger.debug(f"[StreamingBus] publish: {novel_id}, {len(chunk)} chars")
        except Exception as e:
            logger.error(f"[StreamingBus] publish 失败: {e}")

    def subscribe(self, novel_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=1000)
        self._subscribers[novel_id].append(queue)
        return queue

    def unsubscribe(self, novel_id: str, queue: asyncio.Queue):
        if novel_id in self._subscribers:
            try:
                self._subscribers[novel_id].remove(queue)
            except ValueError:
                pass

    def get_chunk(self, novel_id: str, timeout: float = 0.05) -> Optional[str]:
        queue = _get_queue()
        if queue is None:
            logger.debug("[StreamingBus] get_chunk: 队列不可用")
            return None

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                remaining_time = timeout - (time.time() - start_time)
                if remaining_time <= 0:
                    break

                message = queue.get(timeout=min(remaining_time, 0.01))

                if isinstance(message, dict):
                    msg_novel_id = message.get("novel_id")
                    if msg_novel_id == novel_id:
                        return message.get("chunk")
                    else:
                        try:
                            queue.put_nowait(message)
                        except Full:
                            logger.warning(f"[StreamingBus] 无法将消息重新放回队列，小说ID: {msg_novel_id}")

            except Empty:
                time.sleep(0.001)
            except Exception as e:
                logger.debug(f"[StreamingBus] get_chunk 异常: {e}")
                time.sleep(0.001)

        return None

    async def get_chunk_async(self, novel_id: str, timeout: float = 0.05) -> Optional[str]:
        queue = _get_queue()
        if queue is None:
            logger.debug("[StreamingBus] get_chunk_async: 队列不可用")
            return None

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                message = queue.get_nowait()

                if isinstance(message, dict):
                    msg_novel_id = message.get("novel_id")
                    if msg_novel_id == novel_id:
                        return message.get("chunk")
                    else:
                        try:
                            queue.put_nowait(message)
                        except Full:
                            logger.warning(f"[StreamingBus] get_chunk_async: 无法将消息重新放回队列，小说ID: {msg_novel_id}")

            except Empty:
                await asyncio.sleep(0.001)
            except Exception as e:
                logger.debug(f"[StreamingBus] get_chunk_async 异常: {e}")
                await asyncio.sleep(0.001)

        return None

    def get_chunk_non_blocking(self, novel_id: str) -> Optional[str]:
        queue = _get_queue()
        if queue is None:
            return None

        max_checks = 20
        checks = 0

        while checks < max_checks:
            try:
                message = queue.get_nowait()
                checks += 1

                if isinstance(message, dict) and message.get("novel_id") == novel_id:
                    return message.get("chunk")
                else:
                    try:
                        queue.put_nowait(message)
                    except Full:
                        logger.warning("[StreamingBus] get_chunk_non_blocking: 无法重新放回消息")

            except Empty:
                break
            except Exception as e:
                logger.debug(f"[StreamingBus] get_chunk_non_blocking 异常: {e}")
                break

        return None

    def clear(self, novel_id: str):
        queue = _get_queue()
        if queue is None:
            return

        temp_messages = []

        try:
            while True:
                try:
                    message = queue.get_nowait()

                    if isinstance(message, dict) and message.get("novel_id") == novel_id:
                        logger.debug(f"[StreamingBus] 清空队列: 移除小说 {novel_id} 的消息")
                    else:
                        temp_messages.append(message)

                except Empty:
                    break
                except Exception as e:
                    logger.debug(f"[StreamingBus] clear get 异常: {e}")
                    break

            for message in temp_messages:
                try:
                    queue.put_nowait(message)
                except Full:
                    logger.warning("[StreamingBus] clear: 无法将消息重新放回队列")

            logger.debug(f"[StreamingBus] 清空队列完成: {novel_id}, 保留 {len(temp_messages)} 条其他小说消息")

        except Exception as e:
            logger.debug(f"[StreamingBus] clear 异常: {e}")


streaming_bus = StreamingBus()
