"""统一资源管理器 - 管理线程池、缓存、队列等资源的生命周期

核心设计：
1. 所有可托管资源继承 ManagedResource 抽象基类
2. ResourceManager 单例统一管理所有资源
3. 应用退出时自动清理，防止资源泄漏
4. 支持健康检查和资源监控

解决问题：
- SSE 线程池无 shutdown 导致资源残留
- 停止信号字典无限增长
- 共享状态缓存无过期清理
- mp.Queue 消息堆积
"""
import atexit
import logging
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """资源类型枚举"""
    THREAD_POOL = "thread_pool"
    CONNECTION = "connection"
    CACHE = "cache"
    QUEUE = "queue"
    SHARED_STATE = "shared_state"
    STOP_SIGNAL = "stop_signal"


@dataclass
class ResourceMetrics:
    """资源指标"""
    resource_type: ResourceType
    resource_id: str
    created_at: float
    last_used_at: float
    usage_count: int = 0
    size_bytes: int = 0
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "usage_count": self.usage_count,
            "size_bytes": self.size_bytes,
            "is_active": self.is_active,
        }


@dataclass
class ResourceConfig:
    """资源配置"""
    max_lifetime_seconds: float = 7200.0  # 2小时
    idle_timeout_seconds: float = 300.0   # 5分钟
    max_usage_count: int = 10000
    auto_cleanup: bool = True


class ManagedResource(ABC):
    """可托管资源抽象基类

    所有需要生命周期管理的资源都应继承此类，
    实现 shutdown、health_check、get_metrics 方法。
    """

    @property
    @abstractmethod
    def resource_type(self) -> ResourceType:
        """资源类型"""
        ...

    @property
    @abstractmethod
    def resource_id(self) -> str:
        """资源唯一标识"""
        ...

    @abstractmethod
    def shutdown(self, timeout: float = 5.0) -> bool:
        """关闭资源

        Args:
            timeout: 关闭超时时间（秒）

        Returns:
            True 表示成功关闭，False 表示失败
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """健康检查

        Returns:
            True 表示资源健康，False 表示异常
        """
        ...

    @abstractmethod
    def get_metrics(self) -> ResourceMetrics:
        """获取资源指标"""
        ...


class ThreadPoolResource(ManagedResource):
    """线程池资源封装

    封装 ThreadPoolExecutor，提供生命周期管理和指标收集。
    """

    def __init__(
        self,
        executor: ThreadPoolExecutor,
        name: str,
        config: ResourceConfig = None
    ):
        self._executor = executor
        self._name = name
        self._config = config or ResourceConfig()
        self._created_at = time.time()
        self._last_used_at = time.time()
        self._usage_count = 0
        self._lock = threading.Lock()
        self._shutdown = False

    @property
    def resource_type(self) -> ResourceType:
        return ResourceType.THREAD_POOL

    @property
    def resource_id(self) -> str:
        return f"threadpool:{self._name}"

    @property
    def executor(self) -> ThreadPoolExecutor:
        """获取底层执行器"""
        return self._executor

    def submit(self, fn, *args, **kwargs):
        """提交任务并更新指标"""
        with self._lock:
            if self._shutdown:
                raise RuntimeError(f"ThreadPool {self._name} has been shutdown")
            self._usage_count += 1
            self._last_used_at = time.time()
        return self._executor.submit(fn, *args, **kwargs)

    def shutdown(self, timeout: float = 5.0) -> bool:
        if self._shutdown:
            return True

        try:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._shutdown = True
            logger.info(f"[ResourceManager] 线程池 {self._name} 已关闭")
            return True
        except Exception as e:
            logger.warning(f"[ResourceManager] 线程池 {self._name} 关闭失败: {e}")
            return False

    def health_check(self) -> bool:
        if self._shutdown:
            return False
        try:
            # 检查是否有过多待处理任务
            if hasattr(self._executor, '_work_queue'):
                qsize = self._executor._work_queue.qsize()
                return qsize < 100  # 队列不超过100
            return True
        except Exception:
            return False

    def get_metrics(self) -> ResourceMetrics:
        with self._lock:
            return ResourceMetrics(
                resource_type=self.resource_type,
                resource_id=self.resource_id,
                created_at=self._created_at,
                last_used_at=self._last_used_at,
                usage_count=self._usage_count,
                is_active=not self._shutdown,
            )


class CacheResource(ManagedResource):
    """缓存资源封装

    提供 TTL 过期清理和容量限制。
    """

    def __init__(
        self,
        name: str,
        ttl_seconds: float = 60.0,
        max_size: int = 10000,
        config: ResourceConfig = None
    ):
        self._name = name
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._config = config or ResourceConfig()
        self._cache: Dict[str, tuple] = {}  # {key: (timestamp, value)}
        self._lock = threading.Lock()
        self._created_at = time.time()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @property
    def resource_type(self) -> ResourceType:
        return ResourceType.CACHE

    @property
    def resource_id(self) -> str:
        return f"cache:{self._name}"

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            now = time.time()
            if key in self._cache:
                ts, value = self._cache[key]
                if now - ts < self._ttl:
                    self._hits += 1
                    return value
                else:
                    # 过期，删除
                    del self._cache[key]
                    self._evictions += 1
            self._misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        with self._lock:
            now = time.time()
            # 容量检查，触发清理
            if len(self._cache) >= self._max_size:
                self._evict_expired(now)
                # 如果仍然满了，删除最旧的
                if len(self._cache) >= self._max_size:
                    oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                    del self._cache[oldest_key]
                    self._evictions += 1
            self._cache[key] = (now, value)

    def delete(self, key: str) -> bool:
        """删除缓存值"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        """清空缓存，返回清除的条目数"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def _evict_expired(self, now: float) -> int:
        """清理过期条目"""
        expired = [k for k, (ts, _) in self._cache.items() if now - ts >= self._ttl]
        for k in expired:
            del self._cache[k]
        self._evictions += len(expired)
        return len(expired)

    def cleanup_expired(self) -> int:
        """手动清理过期条目"""
        with self._lock:
            return self._evict_expired(time.time())

    def shutdown(self, timeout: float = 5.0) -> bool:
        count = self.clear()
        logger.info(f"[ResourceManager] 缓存 {self._name} 已清理，清除 {count} 条")
        return True

    def health_check(self) -> bool:
        with self._lock:
            return len(self._cache) < self._max_size * 0.9

    def get_metrics(self) -> ResourceMetrics:
        with self._lock:
            return ResourceMetrics(
                resource_type=self.resource_type,
                resource_id=self.resource_id,
                created_at=self._created_at,
                last_used_at=time.time(),
                usage_count=self._hits + self._misses,
                size_bytes=len(self._cache),
                is_active=True,
            )

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "name": self._name,
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": hit_rate,
                "ttl_seconds": self._ttl,
            }


class StopSignalResource(ManagedResource):
    """停止信号资源封装

    管理停止信号字典，定期清理无效条目。
    """

    def __init__(
        self,
        name: str = "default",
        config: ResourceConfig = None
    ):
        self._name = name
        self._config = config or ResourceConfig()
        self._events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._created_at = time.time()
        self._last_cleanup = time.time()

    @property
    def resource_type(self) -> ResourceType:
        return ResourceType.STOP_SIGNAL

    @property
    def resource_id(self) -> str:
        return f"stop_signal:{self._name}"

    def get_or_create(self, key: str) -> threading.Event:
        """获取或创建停止信号"""
        with self._lock:
            if key not in self._events:
                self._events[key] = threading.Event()
            return self._events[key]

    def set(self, key: str) -> None:
        """设置停止信号"""
        with self._lock:
            if key in self._events:
                self._events[key].set()

    def clear(self, key: str) -> None:
        """清除停止信号"""
        with self._lock:
            if key in self._events:
                self._events[key].clear()

    def is_set(self, key: str) -> bool:
        """检查停止信号是否设置"""
        with self._lock:
            if key in self._events:
                return self._events[key].is_set()
            return False

    def cleanup_stale(self, active_keys: Set[str]) -> int:
        """清理不在活跃列表中的信号"""
        with self._lock:
            to_remove = [
                k for k in self._events.keys()
                if k not in active_keys and k != "__all__"
            ]
            for k in to_remove:
                del self._events[k]
            self._last_cleanup = time.time()
            return len(to_remove)

    def shutdown(self, timeout: float = 5.0) -> bool:
        with self._lock:
            count = len(self._events)
            self._events.clear()
            logger.info(f"[ResourceManager] 停止信号 {self._name} 已清理，清除 {count} 条")
            return True

    def health_check(self) -> bool:
        with self._lock:
            # 检查是否需要清理
            if len(self._events) > 100:
                return time.time() - self._last_cleanup < 300  # 5分钟内有清理
            return True

    def get_metrics(self) -> ResourceMetrics:
        with self._lock:
            return ResourceMetrics(
                resource_type=self.resource_type,
                resource_id=self.resource_id,
                created_at=self._created_at,
                last_used_at=self._last_cleanup,
                usage_count=len(self._events),
                size_bytes=len(self._events),
                is_active=True,
            )


class ResourceManager:
    """统一资源管理器 (单例模式)

    核心功能：
    1. 注册/注销资源
    2. 统一关闭所有资源
    3. 健康检查
    4. 空闲资源清理

    使用方式：
        rm = ResourceManager()
        rm.register(thread_pool_resource)
        rm.register(cache_resource)

        # 应用退出时自动清理
        # 或手动调用 rm.shutdown()
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._resources: Dict[str, ManagedResource] = {}
        self._resource_lock = threading.Lock()
        self._shutdown_hooks: List[Callable] = []
        self._initialized = True
        self._shutdown = False

        # 注册应用退出时的清理钩子
        atexit.register(self._atexit_cleanup)

        logger.info("[ResourceManager] 统一资源管理器已初始化")

    def _atexit_cleanup(self):
        """应用退出时的清理"""
        if not self._shutdown:
            self.shutdown()

    def register(self, resource: ManagedResource) -> str:
        """注册资源

        Args:
            resource: 可托管资源

        Returns:
            资源ID
        """
        with self._resource_lock:
            if self._shutdown:
                raise RuntimeError("ResourceManager has been shutdown")

            rid = resource.resource_id
            if rid in self._resources:
                logger.warning(f"[ResourceManager] 资源 {rid} 已存在，将覆盖")
            self._resources[rid] = resource
            logger.debug(f"[ResourceManager] 已注册资源: {rid}")
            return rid

    def unregister(self, resource_id: str) -> bool:
        """注销资源

        Args:
            resource_id: 资源ID

        Returns:
            True 表示成功注销，False 表示资源不存在
        """
        with self._resource_lock:
            if resource_id in self._resources:
                del self._resources[resource_id]
                logger.debug(f"[ResourceManager] 已注销资源: {resource_id}")
                return True
            return False

    def get(self, resource_id: str) -> Optional[ManagedResource]:
        """获取资源"""
        return self._resources.get(resource_id)

    def get_thread_pool(self, name: str) -> Optional[ThreadPoolResource]:
        """获取线程池资源"""
        return self.get(f"threadpool:{name}")

    def get_cache(self, name: str) -> Optional[CacheResource]:
        """获取缓存资源"""
        return self.get(f"cache:{name}")

    def shutdown(self, timeout: float = 10.0) -> None:
        """关闭所有资源

        Args:
            timeout: 总超时时间（秒）
        """
        if self._shutdown:
            return

        self._shutdown = True
        logger.info(f"[ResourceManager] 开始关闭所有资源 (timeout={timeout}s)")

        with self._resource_lock:
            resources = list(self._resources.items())

        if not resources:
            logger.info("[ResourceManager] 无资源需要关闭")
            return

        per_resource_timeout = timeout / max(len(resources), 1)

        for rid, resource in resources:
            try:
                start = time.time()
                success = resource.shutdown(timeout=per_resource_timeout)
                elapsed = time.time() - start
                if success:
                    logger.info(f"[ResourceManager] 资源 {rid} 已关闭 ({elapsed:.2f}s)")
                else:
                    logger.warning(f"[ResourceManager] 资源 {rid} 关闭失败")
            except Exception as e:
                logger.error(f"[ResourceManager] 关闭资源 {rid} 时发生错误: {e}")

        # 执行额外关闭钩子
        for hook in self._shutdown_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"[ResourceManager] 关闭钩子执行失败: {e}")

        with self._resource_lock:
            self._resources.clear()

        logger.info("[ResourceManager] 所有资源已关闭")

    def health_check(self) -> Dict[str, Any]:
        """健康检查所有资源

        Returns:
            {
                "total_resources": int,
                "healthy": int,
                "unhealthy": int,
                "details": {resource_id: {...}}
            }
        """
        result = {
            "total_resources": 0,
            "healthy": 0,
            "unhealthy": 0,
            "details": {}
        }

        with self._resource_lock:
            result["total_resources"] = len(self._resources)
            for rid, resource in self._resources.items():
                try:
                    healthy = resource.health_check()
                    if healthy:
                        result["healthy"] += 1
                    else:
                        result["unhealthy"] += 1
                    result["details"][rid] = {
                        "healthy": healthy,
                        "metrics": resource.get_metrics().to_dict()
                    }
                except Exception as e:
                    result["unhealthy"] += 1
                    result["details"][rid] = {
                        "healthy": False,
                        "error": str(e)
                    }

        return result

    def add_shutdown_hook(self, hook: Callable) -> None:
        """添加关闭钩子"""
        self._shutdown_hooks.append(hook)

    def cleanup_idle(self, idle_threshold_seconds: float = 300) -> int:
        """清理空闲资源

        Args:
            idle_threshold_seconds: 空闲阈值（秒）

        Returns:
            清理的资源数量
        """
        now = time.time()
        cleaned = 0

        with self._resource_lock:
            to_clean = []
            for rid, resource in self._resources.items():
                try:
                    metrics = resource.get_metrics()
                    idle_time = now - metrics.last_used_at
                    if idle_time > idle_threshold_seconds:
                        to_clean.append(rid)
                except Exception:
                    pass

            for rid in to_clean:
                try:
                    self._resources[rid].shutdown()
                    del self._resources[rid]
                    cleaned += 1
                    logger.info(f"[ResourceManager] 已清理空闲资源: {rid}")
                except Exception as e:
                    logger.warning(f"[ResourceManager] 清理资源 {rid} 失败: {e}")

        return cleaned

    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有资源指标"""
        metrics = {}
        with self._resource_lock:
            for rid, resource in self._resources.items():
                try:
                    metrics[rid] = resource.get_metrics().to_dict()
                except Exception as e:
                    metrics[rid] = {"error": str(e)}
        return metrics


# 全局便捷方法
def get_resource_manager() -> ResourceManager:
    """获取资源管理器单例"""
    return ResourceManager()


def create_thread_pool(
    name: str,
    max_workers: int = 12,
    thread_name_prefix: str = None,
) -> ThreadPoolResource:
    """创建并注册线程池资源

    Args:
        name: 线程池名称
        max_workers: 最大工作线程数
        thread_name_prefix: 线程名前缀

    Returns:
        ThreadPoolResource 实例
    """
    executor = ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix=thread_name_prefix or name,
    )
    resource = ThreadPoolResource(executor, name)
    get_resource_manager().register(resource)
    return resource


def create_cache(
    name: str,
    ttl_seconds: float = 60.0,
    max_size: int = 10000,
) -> CacheResource:
    """创建并注册缓存资源

    Args:
        name: 缓存名称
        ttl_seconds: 缓存过期时间（秒）
        max_size: 最大条目数

    Returns:
        CacheResource 实例
    """
    resource = CacheResource(name, ttl_seconds, max_size)
    get_resource_manager().register(resource)
    return resource
