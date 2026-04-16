"""ThemeAgentRegistry — 题材 Agent 注册中心

管理所有题材 Agent 的注册、查找与生命周期。

使用方式：
    registry = ThemeAgentRegistry()
    registry.auto_discover()  # 自动注册内置题材
    agent = registry.get("xuanhuan")  # 按 genre_key 获取

    # 或手动注册自定义题材
    registry.register(MyCustomThemeAgent())

设计原则：
    - 单例友好：可作为全局注册中心使用
    - 自动发现：通过 auto_discover() 扫描 agents/ 目录下的内置实现
    - 安全默认：get() 对未知 genre 返回 None，调用方自行降级
"""

import logging
from typing import Dict, List, Optional

from application.engine.theme.theme_agent import ThemeAgent

logger = logging.getLogger(__name__)


class ThemeAgentRegistry:
    """题材 Agent 注册中心

    管理 genre_key → ThemeAgent 实例的映射。
    支持手动注册和自动发现两种模式。
    """

    def __init__(self):
        self._agents: Dict[str, ThemeAgent] = {}

    def register(self, agent: ThemeAgent) -> None:
        """注册一个题材 Agent

        Args:
            agent: ThemeAgent 实例

        Raises:
            ValueError: 如果 genre_key 已被注册
        """
        key = agent.genre_key
        if key in self._agents:
            existing = self._agents[key]
            logger.warning(
                f"题材 Agent 重复注册：'{key}' "
                f"(已有: {existing.__class__.__name__}, "
                f"新增: {agent.__class__.__name__})，将覆盖旧实例"
            )
        self._agents[key] = agent
        logger.info(f"注册题材 Agent: {agent}")

    def unregister(self, genre_key: str) -> bool:
        """注销一个题材 Agent

        Args:
            genre_key: 题材标识

        Returns:
            是否成功注销（key 存在则为 True）
        """
        if genre_key in self._agents:
            removed = self._agents.pop(genre_key)
            logger.info(f"注销题材 Agent: {removed}")
            return True
        return False

    def get(self, genre_key: str) -> Optional[ThemeAgent]:
        """获取题材 Agent

        Args:
            genre_key: 题材标识（如 'xuanhuan', 'suspense'）

        Returns:
            对应的 ThemeAgent 实例，未注册则返回 None
        """
        return self._agents.get(genre_key)

    def get_or_default(self, genre_key: str) -> Optional[ThemeAgent]:
        """获取题材 Agent，空 key 返回 None

        用于管线中的安全调用：
            agent = registry.get_or_default(novel.genre)
            if agent:
                directives = agent.get_context_directives(...)

        Args:
            genre_key: 题材标识，可为空字符串或 None

        Returns:
            对应的 ThemeAgent 实例，或 None
        """
        if not genre_key:
            return None
        return self._agents.get(genre_key)

    def list_genres(self) -> List[Dict[str, str]]:
        """列出所有已注册的题材

        Returns:
            [{"key": "xuanhuan", "name": "玄幻", "description": "..."}, ...]
        """
        return [
            {
                "key": agent.genre_key,
                "name": agent.genre_name,
                "description": agent.description,
            }
            for agent in self._agents.values()
        ]

    @property
    def registered_keys(self) -> List[str]:
        """已注册的所有 genre_key 列表"""
        return list(self._agents.keys())

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, genre_key: str) -> bool:
        return genre_key in self._agents

    def auto_discover(self) -> int:
        """自动发现并注册 agents/ 目录下的所有内置题材 Agent

        扫描 application.engine.theme.agents 包下所有模块，
        找到 ThemeAgent 的子类并实例化注册。

        Returns:
            成功注册的 Agent 数量
        """
        count = 0

        # (module_name, class_name, display_name)
        _BUILTIN_AGENTS = [
            ("xuanhuan_agent", "XuanhuanThemeAgent", "玄幻"),
            ("dushi_agent", "DushiThemeAgent", "都市"),
            ("scifi_agent", "ScifiThemeAgent", "科幻"),
            ("history_agent", "HistoryThemeAgent", "历史"),
            ("wuxia_agent", "WuxiaThemeAgent", "武侠"),
            ("xianxia_agent", "XianxiaThemeAgent", "仙侠"),
            ("fantasy_agent", "FantasyThemeAgent", "奇幻"),
            ("game_agent", "GameThemeAgent", "游戏"),
            ("suspense_agent", "SuspenseThemeAgent", "悬疑"),
            ("romance_agent", "RomanceThemeAgent", "言情"),
            ("other_agent", "OtherThemeAgent", "其他"),
        ]

        import importlib
        for module_name, class_name, display_name in _BUILTIN_AGENTS:
            try:
                mod = importlib.import_module(
                    f"application.engine.theme.agents.{module_name}"
                )
                cls = getattr(mod, class_name)
                self.register(cls())
                count += 1
            except Exception as e:
                logger.warning(f"加载{display_name}题材 Agent 失败：{e}")

        logger.info(f"自动发现完成，共注册 {count} 个题材 Agent")
        return count

    def __repr__(self) -> str:
        keys = ", ".join(self._agents.keys()) or "(empty)"
        return f"<ThemeAgentRegistry [{keys}]>"
