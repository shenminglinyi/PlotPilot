"""单本小说停止信号（IPC 零延迟）

核心设计：
1. 复用 streaming_bus 的 mp.Queue 传递停止信号消息（无需额外 IPC 通道）
2. 守护进程侧维护 threading.Event 字典（进程内零延迟检查）
3. API /stop 接口双通道：mp.Queue 发消息 + DB UPDATE 兜底

消息传递路径：
  前端 → /stop API → mp.Queue.put(stop_msg) → 守护进程 StreamingBus 消费
                    → DB UPDATE（降级兜底）

守护进程内部：
  StreamingBus 消费到 stop_msg → 设置本地 threading.Event
  _is_still_running() → 检查 threading.Event（亚微秒级）
"""
import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 守护进程侧：本地 threading.Event 字典（进程内零延迟检查）──
_local_stop_events: Dict[str, threading.Event] = {}
_local_lock = threading.Lock()


def _get_or_create_local_event(novel_id: str) -> threading.Event:
    """获取或创建指定小说的本地停止信号（线程安全）"""
    if novel_id not in _local_stop_events:
        with _local_lock:
            if novel_id not in _local_stop_events:
                _local_stop_events[novel_id] = threading.Event()
    return _local_stop_events[novel_id]


def set_local_novel_stop(novel_id: str) -> None:
    """设置指定小说的本地停止信号（守护进程内调用）

    由 StreamingBus.get_chunks_batch() 或 consume_stop_signals() 消费到
    type="stop_signal" 消息后调用。
    """
    evt = _get_or_create_local_event(novel_id)
    if not evt.is_set():
        evt.set()
        logger.info("[NovelStopSignal] 本地停止信号已设置: %s", novel_id)


def clear_local_novel_stop(novel_id: str) -> None:
    """清除指定小说的本地停止信号（守护进程内 /start 时调用）"""
    if novel_id in _local_stop_events:
        _local_stop_events[novel_id].clear()
        logger.info("[NovelStopSignal] 本地停止信号已清除: %s", novel_id)


def is_novel_stopped(novel_id: str) -> bool:
    """检查指定小说是否已收到停止信号（守护进程调用，亚微秒级）

    这是守护进程检查停止信号的主入口。
    """
    if novel_id not in _local_stop_events:
        return False
    return _local_stop_events[novel_id].is_set()


def publish_stop_signal(novel_id: str) -> None:
    """通过 mp.Queue 发布停止信号（API /stop 调用，主进程侧）

    将停止信号消息放入 streaming_bus 的 mp.Queue，
    守护进程消费到后调用 set_local_novel_stop()。
    """
    from application.engine.services.streaming_bus import streaming_bus
    streaming_bus.publish_stop_signal(novel_id)
    logger.info("[NovelStopSignal] 停止信号已通过 StreamingBus 发布: %s", novel_id)


def publish_start_signal(novel_id: str) -> None:
    """通过 mp.Queue 发布启动信号（API /start 调用，主进程侧）

    守护进程消费到后调用 clear_local_novel_stop()，
    清除本地 threading.Event 以便小说可以重新启动。
    """
    from application.engine.services.streaming_bus import streaming_bus
    streaming_bus.publish_start_signal(novel_id)
    logger.info("[NovelStopSignal] 启动信号已通过 StreamingBus 发布: %s", novel_id)


def inject_novel_stop_events(events: dict = None) -> None:
    """兼容旧接口：守护进程子进程注入（现无实际操作，因为改为 Queue 驱动）"""
    logger.info("[NovelStopSignal] 守护进程停止信号模块已就绪（Queue 驱动模式）")


def cleanup_stale_stop_signals(active_novel_ids: set) -> int:
    """清理不在活跃列表中的停止信号（解决内存泄漏问题）

    当小说完成或删除后，对应的停止信号不再需要，应清理以释放内存。

    Args:
        active_novel_ids: 当前活跃的小说 ID 集合

    Returns:
        清理的信号数量
    """
    cleaned = 0
    with _local_lock:
        to_remove = [
            nid for nid in _local_stop_events.keys()
            if nid not in active_novel_ids and nid != "__all__"
        ]
        for nid in to_remove:
            del _local_stop_events[nid]
            cleaned += 1

    if cleaned > 0:
        logger.info("[NovelStopSignal] 清理了 %d 个过期的停止信号", cleaned)

    return cleaned


def get_stop_signal_count() -> int:
    """获取当前停止信号数量"""
    with _local_lock:
        return len(_local_stop_events)


def get_all_stop_signal_ids() -> List[str]:
    """获取所有停止信号对应的小说 ID"""
    with _local_lock:
        return list(_local_stop_events.keys())


def clear_all_stop_signals() -> int:
    """清除所有停止信号（应用关闭时调用）"""
    with _local_lock:
        count = len(_local_stop_events)
        _local_stop_events.clear()
        return count
