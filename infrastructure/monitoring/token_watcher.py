"""TokenWatcher 中间件 - 监控 LLM 调用"""
import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from typing import Optional, Any, Dict

from infrastructure.monitoring.monitoring_db import get_monitoring_db

logger = logging.getLogger(__name__)


@dataclass
class TokenLogEntry:
    """Token 日志条目"""
    model: str
    provider: str
    operation_type: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    success: bool
    error_message: Optional[str] = None
    request_preview: Optional[str] = None
    response_preview: Optional[str] = None


@dataclass
class TokenWatcherConfig:
    """TokenWatcher 配置"""
    enabled: bool = False
    paginate: int = 20
    usage_only: bool = True


class TokenWatcher:
    """Token 监控器（线程安全单例）"""
    _instance: Optional['TokenWatcher'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'TokenWatcher':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._db = get_monitoring_db()
        self._load_config()

    def _load_config(self):
        """从数据库加载配置"""
        enabled = self._db.get_config('enabled', '0') == '1'
        paginate = int(self._db.get_config('paginate', '20'))
        usage_only = self._db.get_config('usage_only', '1') == '1'
        self._config = TokenWatcherConfig(
            enabled=enabled,
            paginate=paginate,
            usage_only=usage_only
        )

    def _save_config(self):
        """保存配置到数据库"""
        self._db.set_config('enabled', '1' if self._config.enabled else '0')
        self._db.set_config('paginate', str(self._config.paginate))
        self._db.set_config('usage_only', '1' if self._config.usage_only else '0')

    @property
    def config(self) -> TokenWatcherConfig:
        return self._config

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def update_config(self, enabled: Optional[bool] = None, paginate: Optional[int] = None, usage_only: Optional[bool] = None):
        """更新配置"""
        if enabled is not None:
            self._config.enabled = enabled
        if paginate is not None:
            self._config.paginate = paginate
        if usage_only is not None:
            self._config.usage_only = usage_only
        self._save_config()

    def log(self, entry: TokenLogEntry) -> None:
        """记录 token 使用日志"""
        if not self._config.enabled:
            return

        try:
            request_preview = None
            response_preview = None

            if not self._config.usage_only:
                request_preview = entry.request_preview
                response_preview = entry.response_preview

            self._db.execute(
                '''INSERT INTO token_logs 
                   (model, provider, operation_type, input_tokens, output_tokens, total_tokens,
                    latency_ms, success, error_message, request_preview, response_preview)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    entry.model,
                    entry.provider,
                    entry.operation_type,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.total_tokens,
                    entry.latency_ms,
                    1 if entry.success else 0,
                    entry.error_message,
                    request_preview,
                    response_preview,
                )
            )
            self._db.commit()
        except Exception as e:
            logger.warning(f'TokenWatcher log failed: {e}')

    def record_call(
        self,
        model: str,
        provider: str,
        operation_type: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        success: bool,
        error_message: Optional[str] = None,
        request_data: Optional[Any] = None,
        response_data: Optional[Any] = None,
    ) -> None:
        """记录一次 LLM 调用"""
        if not self._config.enabled:
            return

        request_preview = None
        response_preview = None

        if not self._config.usage_only:
            try:
                if request_data:
                    request_str = json.dumps(request_data, ensure_ascii=False)
                    request_preview = request_str[:2000]
                if response_data:
                    response_str = json.dumps(response_data, ensure_ascii=False)
                    response_preview = response_str[:2000]
            except Exception:
                pass

        entry = TokenLogEntry(
            model=model,
            provider=provider,
            operation_type=operation_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            request_preview=request_preview,
            response_preview=response_preview,
        )
        self.log(entry)

    def get_logs(self, page: int = 1, page_size: Optional[int] = None) -> Dict[str, Any]:
        """获取分页日志"""
        if page_size is None:
            page_size = self._config.paginate

        offset = (page - 1) * page_size

        total_row = self._db.fetch_one('SELECT COUNT(*) as count FROM token_logs')
        total = total_row['count'] if total_row else 0

        rows = self._db.fetch_all(
            '''SELECT * FROM token_logs 
               ORDER BY timestamp DESC 
               LIMIT ? OFFSET ?''',
            (page_size, offset)
        )

        logs = [dict(row) for row in rows]

        return {
            'logs': logs,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size if page_size > 0 else 0,
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取 token 使用汇总"""
        row = self._db.fetch_one('''
            SELECT 
                COUNT(*) as total_calls,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(total_tokens) as total_tokens,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count,
                AVG(latency_ms) as avg_latency_ms
            FROM token_logs
        ''')

        if not row or row['total_calls'] == 0:
            return {
                'total_calls': 0,
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_tokens': 0,
                'success_count': 0,
                'error_count': 0,
                'avg_latency_ms': 0.0,
            }

        return {
            'total_calls': row['total_calls'] or 0,
            'total_input_tokens': row['total_input_tokens'] or 0,
            'total_output_tokens': row['total_output_tokens'] or 0,
            'total_tokens': row['total_tokens'] or 0,
            'success_count': row['success_count'] or 0,
            'error_count': row['error_count'] or 0,
            'avg_latency_ms': row['avg_latency_ms'] or 0.0,
        }

    def clear_logs(self) -> int:
        """清空所有日志"""
        result = self._db.execute('DELETE FROM token_logs')
        self._db.commit()
        return result.rowcount

    def delete_log(self, log_id: int) -> bool:
        """删除单条日志"""
        result = self._db.execute('DELETE FROM token_logs WHERE id = ?', (log_id,))
        self._db.commit()
        return result.rowcount > 0


def get_token_watcher() -> TokenWatcher:
    return TokenWatcher()


class TokenWatcherContext:
    """TokenWatcher 上下文管理器，用于测量调用耗时"""

    def __init__(
        self,
        model: str,
        provider: str,
        operation_type: str,
    ):
        self.model = model
        self.provider = provider
        self.operation_type = operation_type
        self.start_time = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.success = True
        self.error_message = None
        self.request_data = None
        self.response_data = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_ms = int((time.perf_counter() - self.start_time) * 1000)

        if exc_type is not None:
            self.success = False
            self.error_message = str(exc_val)

        watcher = get_token_watcher()
        watcher.record_call(
            model=self.model,
            provider=self.provider,
            operation_type=self.operation_type,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            latency_ms=latency_ms,
            success=self.success,
            error_message=self.error_message,
            request_data=self.request_data,
            response_data=self.response_data,
        )
        return False

    def set_tokens(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def set_request(self, data: Any):
        self.request_data = data

    def set_response(self, data: Any):
        self.response_data = data

    def set_error(self, message: str):
        self.success = False
        self.error_message = message
