"""TokenWatcher 配置模块"""
from pathlib import Path


def get_monitoring_db_path() -> Path:
    """获取 monitoring.db 数据库路径"""
    root = Path(__file__).resolve().parents[2]
    data_dir = root / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'monitoring.db'


def get_token_logs_dir() -> Path:
    """获取 token 日志目录路径"""
    root = Path(__file__).resolve().parents[2]
    logs_dir = root / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir
