"""配置加载器 - 统一配置管理

使用方法：
    from config import get_config

    config = get_config()
    max_attempts = config.performance.autopilot.voice_rewrite.max_attempts
"""
import yaml
from pathlib import Path
from typing import Any, Dict
from dataclasses import dataclass


@dataclass
class ConfigAccessor:
    """配置访问器（支持点号访问）"""
    _data: Dict[str, Any]

    def __getattr__(self, key: str) -> Any:
        if key.startswith('_'):
            return super().__getattribute__(key)

        value = self._data.get(key)
        if isinstance(value, dict):
            return ConfigAccessor(value)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """安全获取配置"""
        return self._data.get(key, default)


class ConfigLoader:
    """配置加载器"""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: str = None) -> ConfigAccessor:
        """加载配置文件

        Args:
            config_path: 配置文件路径（默认使用项目根目录的 config/performance.yaml）

        Returns:
            ConfigAccessor 实例
        """
        if self._config is not None:
            return self._config

        if config_path is None:
            # 默认配置路径
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config" / "performance.yaml"

        config_path = Path(config_path)
        if not config_path.exists():
            print(f"⚠️  配置文件不存在: {config_path}，使用默认配置")
            return ConfigAccessor({})

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            self._config = ConfigAccessor(data)
            return self._config

        except Exception as e:
            print(f"❌ 加载配置失败: {e}，使用默认配置")
            return ConfigAccessor({})

    def reload(self, config_path: str = None) -> ConfigAccessor:
        """重新加载配置"""
        self._config = None
        return self.load(config_path)


# 全局实例
_config_loader = ConfigLoader()


def get_config() -> ConfigAccessor:
    """获取全局配置实例"""
    return _config_loader.load()


def reload_config(config_path: str = None) -> ConfigAccessor:
    """重新加载配置"""
    return _config_loader.reload(config_path)
