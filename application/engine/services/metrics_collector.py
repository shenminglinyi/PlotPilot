"""性能监控指标收集器

收集关键性能指标，支持告警和诊断。

关键指标：
- 数据库锁等待时间
- API 响应时间
- 持久化队列深度
- 守护进程轮询周期
"""
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str]


class MetricsCollector:
    """指标收集器"""

    # 指标保留时长（秒）
    METRIC_RETENTION = 3600  # 1 小时

    # 告警规则
    ALERT_RULES = {
        "db_lock_wait_time": {
            "operator": ">",
            "threshold": 1.0,
            "message": "数据库锁等待超过 1 秒",
            "severity": "warning",
        },
        "api_response_time": {
            "operator": ">",
            "threshold": 0.5,
            "message": "API 响应超过 500ms",
            "severity": "warning",
        },
        "persistence_queue_depth": {
            "operator": ">",
            "threshold": 100,
            "message": "持久化队列积压超过 100",
            "severity": "warning",
        },
        "daemon_loop_time": {
            "operator": ">",
            "threshold": 10.0,
            "message": "守护进程轮询周期超过 10 秒",
            "severity": "warning",
        },
        "db_connection_wait_time": {
            "operator": ">",
            "threshold": 0.1,
            "message": "数据库连接等待超过 100ms",
            "severity": "info",
        },
    }

    def __init__(self, retention_seconds: int = None):
        self._retention = retention_seconds or self.METRIC_RETENTION
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._lock = threading.RLock()
        self._alert_handlers: List[Callable] = []

    def record(self, name: str, value: float, tags: Dict[str, str] = None):
        """记录指标

        Args:
            name: 指标名称
            value: 指标值
            tags: 标签（用于分组）
        """
        metric = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags or {}
        )

        with self._lock:
            self._metrics[name].append(metric)

        # 检查告警
        self._check_alert(name, value, tags)

    def time_it(self, name: str, tags: Dict[str, str] = None):
        """计时上下文管理器

        Usage:
            with metrics.time_it("api_response_time", {"endpoint": "/api/novels"}):
                # ... 处理请求 ...
        """
        start = time.time()

        class Timer:
            def __init__(inner_self, metric_name, metric_tags):
                inner_self.name = metric_name
                inner_self.tags = metric_tags

            def __enter__(inner_self):
                return inner_self

            def __exit__(inner_self, *args):
                elapsed = time.time() - start
                self.record(inner_self.name, elapsed, inner_self.tags)

        return Timer(name, tags)

    def increment(self, name: str, value: float = 1.0, tags: Dict[str, str] = None):
        """计数器增量"""
        self.record(name, value, tags)

    def gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """记录仪表盘值"""
        self.record(name, value, tags)

    def _check_alert(self, name: str, value: float, tags: Dict[str, str]):
        """检查告警规则"""
        if name not in self.ALERT_RULES:
            return

        rule = self.ALERT_RULES[name]
        operator = rule["operator"]
        threshold = rule["threshold"]
        message = rule["message"]
        severity = rule.get("severity", "warning")

        triggered = False
        if operator == ">" and value > threshold:
            triggered = True
        elif operator == "<" and value < threshold:
            triggered = True
        elif operator == "==" and value == threshold:
            triggered = True

        if triggered:
            alert = {
                "name": name,
                "value": value,
                "threshold": threshold,
                "message": message,
                "severity": severity,
                "tags": tags,
                "timestamp": datetime.now().isoformat(),
            }

            # 记录日志
            if severity == "error":
                logger.error(f"🚨 告警: {message} | {name}={value:.2f} > {threshold}")
            elif severity == "warning":
                logger.warning(f"⚠️  告警: {message} | {name}={value:.2f} > {threshold}")
            else:
                logger.info(f"ℹ️  告警: {message} | {name}={value:.2f} > {threshold}")

            # 调用告警处理器
            for handler in self._alert_handlers:
                try:
                    handler(alert)
                except Exception as e:
                    logger.error(f"告警处理器异常: {e}")

    def register_alert_handler(self, handler: Callable):
        """注册告警处理器"""
        self._alert_handlers.append(handler)

    def get_metrics(self, name: str, since: float = None) -> List[MetricPoint]:
        """获取指标历史

        Args:
            name: 指标名称
            since: 起始时间戳

        Returns:
            指标数据点列表
        """
        with self._lock:
            metrics = list(self._metrics.get(name, []))

        if since:
            metrics = [m for m in metrics if m.timestamp >= since]

        return metrics

    def get_summary(self, name: str, window_seconds: int = 300) -> Dict:
        """获取指标摘要统计

        Args:
            name: 指标名称
            window_seconds: 时间窗口（秒）

        Returns:
            统计摘要
        """
        since = time.time() - window_seconds
        metrics = self.get_metrics(name, since)

        if not metrics:
            return {"count": 0}

        values = [m.value for m in metrics]

        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "p50": self._percentile(values, 50),
            "p95": self._percentile(values, 95),
            "p99": self._percentile(values, 99),
        }

    def _percentile(self, values: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def get_all_summaries(self) -> Dict[str, Dict]:
        """获取所有指标摘要"""
        with self._lock:
            names = list(self._metrics.keys())

        return {name: self.get_summary(name) for name in names}

    def cleanup_old_metrics(self):
        """清理过期指标"""
        cutoff = time.time() - self._retention

        with self._lock:
            for name in list(self._metrics.keys()):
                # deque 会自动清理，但我们可以主动移除旧数据
                metrics = self._metrics[name]
                while metrics and metrics[0].timestamp < cutoff:
                    metrics.popleft()

    def export_prometheus(self) -> str:
        """导出 Prometheus 格式指标"""
        lines = []

        for name, summary in self.get_all_summaries().items():
            if summary["count"] == 0:
                continue

            # Prometheus 格式
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"# HELP {name} Performance metric: {name}")
            lines.append(f"{name}_count {summary['count']}")
            lines.append(f"{name}_min {summary['min']:.3f}")
            lines.append(f"{name}_max {summary['max']:.3f}")
            lines.append(f"{name}_avg {summary['avg']:.3f}")
            lines.append(f"{name}_p50 {summary['p50']:.3f}")
            lines.append(f"{name}_p95 {summary['p95']:.3f}")
            lines.append(f"{name}_p99 {summary['p99']:.3f}")
            lines.append("")

        return "\n".join(lines)


# 全局实例
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
