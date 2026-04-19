"""TokenWatcher 中间件 - 监控 LLM 调用"""
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict, List

from infrastructure.monitoring.monitoring_db import get_monitoring_db
from infrastructure.monitoring.token_watcher_config import get_token_logs_dir

logger = logging.getLogger(__name__)

_LOG_MAX_BYTES = 10 * 1024 * 1024


@dataclass
class TokenLogEntry:
    """Token 日志条目"""
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None
    request_data: Optional[Any] = None
    response_data: Optional[Any] = None


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
        if getattr(self, '_initialized', False):
            return
        try:
            self._db = get_monitoring_db()
            self._load_config()
            self._initialized = True
        except Exception as e:
            logger.error(f"TokenWatcher initialization failed: {e}")
            self._db = None
            self._config = TokenWatcherConfig()
            self._initialized = True

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
        if self._db is None:
            return
        self._db.set_config('enabled', '1' if self._config.enabled else '0')
        self._db.set_config('paginate', str(self._config.paginate))
        self._db.set_config('usage_only', '1' if self._config.usage_only else '0')

    @property
    def config(self) -> TokenWatcherConfig:
        return self._config

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def _check_db(self) -> bool:
        """检查数据库是否可用"""
        return self._db is not None

    def update_config(self, enabled: Optional[bool] = None, paginate: Optional[int] = None, usage_only: Optional[bool] = None):
        """更新配置"""
        if not self._check_db():
            return
        if enabled is not None:
            self._config.enabled = enabled
        if paginate is not None:
            self._config.paginate = paginate
        if usage_only is not None:
            self._config.usage_only = usage_only
        self._save_config()

    def log(self, entry: TokenLogEntry) -> None:
        """记录 token 使用日志"""
        if not self._config.enabled or self._db is None:
            return

        try:
            # 当详情记录开启时，保存 request/response 到文件
            if not self._config.usage_only and (entry.request_data or entry.response_data):
                self._save_detail_to_file(entry)

            self._db.execute(
                '''INSERT INTO token_logs
                   (model, provider, input_tokens, output_tokens, total_tokens,
                    latency_ms, success, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    entry.model,
                    entry.provider,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.total_tokens,
                    entry.latency_ms,
                    1 if entry.success else 0,
                    entry.error_message,
                )
            )

            # 更新统计表
            self._update_stats(entry)

            self._db.commit()
        except Exception as e:
            logger.warning(f'TokenWatcher log failed: {e}')

    def _save_detail_to_file(self, entry: TokenLogEntry) -> None:
        """保存详情到日志文件（带轮转）"""
        try:
            logs_dir = get_token_logs_dir()
            log_file = logs_dir / 'token.log'

            # 轮转：超过大小上限则重命名为 .old
            if log_file.exists() and log_file.stat().st_size > _LOG_MAX_BYTES:
                old_file = logs_dir / 'token.log.old'
                if old_file.exists():
                    old_file.unlink()
                log_file.rename(old_file)

            detail_data = {
                'timestamp': datetime.now().isoformat(),
                'provider': entry.provider,
                'model': entry.model,
                'input_tokens': entry.input_tokens,
                'output_tokens': entry.output_tokens,
                'total_tokens': entry.total_tokens,
                'latency_ms': entry.latency_ms,
                'success': entry.success,
                'error_message': entry.error_message,
                'request': entry.request_data,
                'response': entry.response_data,
            }

            log_line = json.dumps(detail_data, ensure_ascii=False, default=str)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_line + '\n')
        except Exception as e:
            logger.warning(f'Failed to save detail to file: {e}')

    def _update_stats(self, entry: TokenLogEntry) -> None:
        """更新 token 统计表（按 provider + model 分组）"""
        self._db.execute(
            '''INSERT INTO token_stats 
               (provider, model, total_calls, total_input_tokens, total_output_tokens,
                total_tokens, total_latency_ms)
               VALUES (?, ?, 1, ?, ?, ?, ?)
               ON CONFLICT(provider, model) DO UPDATE SET
                   total_calls = total_calls + 1,
                   total_input_tokens = total_input_tokens + excluded.total_input_tokens,
                   total_output_tokens = total_output_tokens + excluded.total_output_tokens,
                   total_tokens = total_tokens + excluded.total_tokens,
                   total_latency_ms = total_latency_ms + excluded.total_latency_ms,
                   updated_at = datetime('now', 'localtime')''',
            (
                entry.provider,
                entry.model,
                entry.input_tokens,
                entry.output_tokens,
                entry.total_tokens,
                entry.latency_ms,
            )
        )

    def record_call(
        self,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
        request_data: Optional[Any] = None,
        response_data: Optional[Any] = None,
    ) -> None:
        """记录一次 LLM 调用"""
        if not self._config.enabled:
            return

        if not success:
            return

        entry = TokenLogEntry(
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            request_data=request_data,
            response_data=response_data,
        )
        self.log(entry)

    def get_logs(
        self,
        page: int = 1,
        page_size: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取分页日志"""
        if not self._check_db():
            return {'logs': [], 'total': 0, 'page': page, 'page_size': page_size or 20, 'total_pages': 0}
        if page_size is None:
            page_size = self._config.paginate

        offset = (page - 1) * page_size

        conditions, params = self._build_filter_conditions(provider, model, time_range)
        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        total_row = self._db.fetch_one(
            f'SELECT COUNT(*) as count FROM token_logs WHERE {where_clause}',
            tuple(params)
        )
        total = total_row['count'] if total_row else 0

        rows = self._db.fetch_all(
            f'''SELECT id, timestamp, model, provider, input_tokens, output_tokens,
                       total_tokens, latency_ms, success, error_message
               FROM token_logs
               WHERE {where_clause}
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?''',
            tuple(params) + (page_size, offset)
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
        if not self._check_db():
            return {
                'total_calls': 0,
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_tokens': 0,
                'avg_latency_ms': 0.0,
            }
        row = self._db.fetch_one('''
            SELECT 
                SUM(total_calls) as total_calls,
                SUM(total_input_tokens) as total_input_tokens,
                SUM(total_output_tokens) as total_output_tokens,
                SUM(total_tokens) as total_tokens,
                SUM(total_latency_ms) as total_latency_ms
            FROM token_stats
        ''')

        if not row or row['total_calls'] == 0:
            return {
                'total_calls': 0,
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_tokens': 0,
                'avg_latency_ms': 0.0,
            }

        total_calls = row['total_calls'] or 0
        avg_latency = 0.0
        if total_calls > 0:
            avg_latency = (row['total_latency_ms'] or 0) / total_calls

        return {
            'total_calls': total_calls,
            'total_input_tokens': row['total_input_tokens'] or 0,
            'total_output_tokens': row['total_output_tokens'] or 0,
            'total_tokens': row['total_tokens'] or 0,
            'avg_latency_ms': avg_latency,
        }

    def get_stats_by_dimension(
        self,
        group_by: str = 'provider',
        provider: Optional[str] = None,
        model: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> list:
        """按维度查询统计数据"""
        if not self._check_db():
            return []
        valid_group_by = ['provider', 'model', 'provider_model']
        if group_by not in valid_group_by:
            group_by = 'provider'

        conditions, params = self._build_filter_conditions(provider, model, time_range)
        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        if group_by == 'provider_model':
            group_fields = 'provider, model'
            select_fields = 'provider, model'
        else:
            group_fields = group_by
            select_fields = group_by

        # 有时间筛选时从日志表实时计算，否则从统计表获取
        if time_range:
            rows = self._db.fetch_all(
                f'''
                SELECT 
                    {select_fields},
                    COUNT(*) as total_calls,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(total_tokens) as total_tokens,
                    SUM(latency_ms) as total_latency_ms
                FROM token_logs
                WHERE {where_clause}
                GROUP BY {group_fields}
                ORDER BY total_tokens DESC
                ''',
                tuple(params)
            )
        else:
            rows = self._db.fetch_all(
                f'''
                SELECT 
                    {select_fields},
                    SUM(total_calls) as total_calls,
                    SUM(total_input_tokens) as total_input_tokens,
                    SUM(total_output_tokens) as total_output_tokens,
                    SUM(total_tokens) as total_tokens,
                    SUM(total_latency_ms) as total_latency_ms
                FROM token_stats
                WHERE {where_clause}
                GROUP BY {group_fields}
                ORDER BY total_tokens DESC
                ''',
                tuple(params)
            )

        result = []
        for row in rows:
            total_calls = row['total_calls'] or 0
            avg_latency = 0.0
            if total_calls > 0:
                avg_latency = (row['total_latency_ms'] or 0) / total_calls

            item = {
                'total_calls': total_calls,
                'total_input_tokens': row['total_input_tokens'] or 0,
                'total_output_tokens': row['total_output_tokens'] or 0,
                'total_tokens': row['total_tokens'] or 0,
                'avg_latency_ms': avg_latency,
            }

            if group_by == 'provider_model':
                item['provider'] = row['provider']
                item['model'] = row['model']
            else:
                item[group_by] = row[group_by]

            result.append(item)

        return result

    def get_filters(self) -> Dict[str, List[str]]:
        """获取可用的筛选选项"""
        if not self._check_db():
            return {'providers': [], 'models': []}
        log_providers = self._db.fetch_all(
            'SELECT DISTINCT provider FROM token_logs ORDER BY provider'
        )
        log_models = self._db.fetch_all(
            'SELECT DISTINCT model FROM token_logs ORDER BY model'
        )

        stats_providers = self._db.fetch_all(
            'SELECT DISTINCT provider FROM token_stats ORDER BY provider'
        )
        stats_models = self._db.fetch_all(
            'SELECT DISTINCT model FROM token_stats ORDER BY model'
        )

        providers = set(row['provider'] for row in log_providers)
        providers.update(row['provider'] for row in stats_providers)

        models = set(row['model'] for row in log_models)
        models.update(row['model'] for row in stats_models)

        return {
            'providers': sorted(providers),
            'models': sorted(models),
        }

    def export_logs(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """导出日志数据"""
        if not self._check_db():
            return []
        conditions, params = self._build_filter_conditions(provider, model, time_range)
        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        rows = self._db.fetch_all(
            f'''SELECT id, timestamp, model, provider, input_tokens, output_tokens,
                       total_tokens, latency_ms, success, error_message
               FROM token_logs
               WHERE {where_clause}
               ORDER BY timestamp DESC''',
            tuple(params)
        )

        return [dict(row) for row in rows]

    def reset_stats(self) -> int:
        """重置统计数据（同时清空日志）"""
        if not self._check_db():
            return 0
        stats_result = self._db.execute('DELETE FROM token_stats')
        logs_result = self._db.execute('DELETE FROM token_logs')
        self._db.commit()
        return stats_result.rowcount + logs_result.rowcount

    def _build_filter_conditions(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> tuple:
        """构建筛选条件，返回 (conditions, params)"""
        conditions = []
        params = []
        if provider:
            conditions.append('provider = ?')
            params.append(provider)
        if model:
            conditions.append('model = ?')
            params.append(model)
        if time_range:
            if time_range == 'today':
                conditions.append("date(timestamp) = date('now', 'localtime')")
            elif time_range == 'week':
                conditions.append("timestamp >= datetime('now', '-7 days', 'localtime')")
            elif time_range == 'month':
                conditions.append("timestamp >= datetime('now', '-30 days', 'localtime')")
        return conditions, params


def get_token_watcher() -> TokenWatcher:
    return TokenWatcher()
