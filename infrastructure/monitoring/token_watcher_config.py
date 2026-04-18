"""TokenWatcher 配置模块"""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TokenWatcherConfig:
    """TokenWatcher 配置"""
    enabled: bool = False
    paginate: int = 20
    usage_only: bool = True

    @classmethod
    def from_env(cls) -> 'TokenWatcherConfig':
        """从环境变量读取配置"""
        return cls(
            enabled=os.getenv('TOKEN_WATCHER', '0') == '1',
            paginate=int(os.getenv('TOKEN_PAGINATE', '20')),
            usage_only=os.getenv('TOKEN_USAGE_ONLY', '1') == '1',
        )


def get_monitoring_db_path() -> Path:
    """获取 monitoring.db 数据库路径"""
    root = Path(__file__).resolve().parents[2]
    data_dir = root / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'monitoring.db'
