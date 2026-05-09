"""持久化队列适配器 - 向后兼容层

提供新旧队列的无缝切换，确保平滑迁移。

使用方式：
1. 默认使用新的 SQLite 持久化队列（推荐）
2. 如果初始化失败，降级到旧的内存队列
3. 现有代码无需修改，透明切换
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PersistenceQueueAdapter:
    """持久化队列适配器（兼容新旧实现）"""

    def __init__(self):
        self._impl = None
        self._use_v2 = False

        # 尝试初始化 V2 队列
        try:
            from infrastructure.persistence.database.connection import get_connection_pool
            from application.engine.services.persistence_queue_v2 import PersistentQueueV2

            db_pool = get_connection_pool()
            self._impl = PersistentQueueV2(db_pool)
            self._use_v2 = True
            logger.info("✅ 使用持久化队列 V2 (SQLite)")

        except Exception as e:
            logger.warning(f"初始化持久化队列 V2 失败，降级到 V1: {e}")

            try:
                from application.engine.services.persistence_queue import (
                    PersistenceQueue,
                    get_persistence_queue,
                )
                self._impl = get_persistence_queue()
                self._use_v2 = False
                logger.info("✅ 使用持久化队列 V1 (内存)")

            except Exception as e2:
                logger.error(f"初始化持久化队列失败: {e2}")
                raise RuntimeError("无法初始化持久化队列")

    def push(self, command_type: str, payload: Dict[str, Any], **kwargs) -> bool:
        """推入命令"""
        try:
            if self._use_v2:
                # V2 支持优先级和重试次数
                return self._impl.push(command_type, payload, **kwargs)
            else:
                # V1 只支持基本参数
                return self._impl.push(command_type, payload)
        except Exception as e:
            logger.error(f"推入命令失败: {command_type}, {e}")
            return False

    def start_consumer(self):
        """启动消费者"""
        self._impl.start_consumer()

    def stop_consumer(self):
        """停止消费者"""
        self._impl.stop_consumer()

    def register_handler(self, command_type: str, handler):
        """注册处理器"""
        self._impl.register_handler(command_type, handler)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self._impl.get_stats()

    @property
    def is_v2(self) -> bool:
        """是否使用 V2 队列"""
        return self._use_v2


# 全局实例
_queue_adapter: Optional[PersistenceQueueAdapter] = None


def get_persistence_queue_adapter() -> PersistenceQueueAdapter:
    """获取全局队列适配器"""
    global _queue_adapter
    if _queue_adapter is None:
        _queue_adapter = PersistenceQueueAdapter()
    return _queue_adapter
