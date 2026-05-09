"""通用主题代理 - 配置驱动的题材处理

使用方法：
    from application.engine.theme.generic_theme_agent import GenericThemeAgent
    from config import get_config

    config = get_config().themes.wuxia
    agent = GenericThemeAgent(config)
"""
from typing import Dict, List, Optional
import yaml
from pathlib import Path

from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class GenericThemeAgent(ThemeAgent):
    """通用主题代理 - 配置驱动

    核心改进：
    1. 配置驱动：题材定义从代码迁移到 YAML
    2. 无重复代码：所有题材共用同一代理类
    3. 易扩展：新增题材只需添加配置文件
    """

    def __init__(self, config: Dict):
        """初始化主题代理

        Args:
            config: 题材配置（字典或 ConfigAccessor）
        """
        self.config = config
        self._beat_templates = None

    @property
    def genre_key(self) -> str:
        return self.config.get("genre_key", "unknown")

    @property
    def genre_name(self) -> str:
        return self.config.get("genre_name", "未知题材")

    @property
    def description(self) -> str:
        return self.config.get("description", "")

    def get_system_persona(self) -> str:
        """获取 AI 人设"""
        return self.config.get("system_persona", "你是一位专业的小说作家。")

    def get_writing_rules(self) -> List[str]:
        """获取写作规则"""
        return self.config.get("writing_rules", [])

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        """获取上下文指导"""
        return ThemeDirectives(
            world_rules=self.config.get("world_rules", ""),
            atmosphere=self.config.get("atmosphere", ""),
            taboos="\n".join(self.config.get("taboos", [])),
            tropes_to_use="\n".join(self.config.get("tropes_to_use", [])),
            tropes_to_avoid="\n".join(self.config.get("tropes_to_avoid", [])),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        """获取节拍模板"""
        if self._beat_templates is not None:
            return self._beat_templates

        templates = []
        for template_data in self.config.get("beat_templates", []):
            templates.append(BeatTemplate(
                keywords=template_data.get("keywords", []),
                priority=template_data.get("priority", 50),
                beats=template_data.get("template", "").split("\n"),
            ))

        self._beat_templates = templates
        return templates

    def get_audit_criteria(
        self,
        novel_id: str,
        chapter_number: int,
        chapter_content: str,
    ) -> ThemeAuditCriteria:
        """获取审计标准"""
        criteria = self.config.get("audit_criteria", {})

        return ThemeAuditCriteria(
            style_requirements=criteria.get("style_requirements", []),
            taboos_check=criteria.get("taboos_check", []),
            quality_metrics=criteria.get("quality_metrics", {}),
        )

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "GenericThemeAgent":
        """从 YAML 文件加载题材配置

        Args:
            yaml_path: YAML 配置文件路径

        Returns:
            GenericThemeAgent 实例
        """
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return cls(config)


class ThemeAgentFactory:
    """主题代理工厂

    用法：
        factory = ThemeAgentFactory("application/engine/theme/configs")
        wuxia_agent = factory.get_agent("wuxia")
        xianxia_agent = factory.get_agent("xianxia")
    """

    def __init__(self, config_dir: str):
        """初始化工厂

        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = Path(config_dir)
        self._agents: Dict[str, GenericThemeAgent] = {}

    def get_agent(self, genre_key: str) -> GenericThemeAgent:
        """获取题材代理

        Args:
            genre_key: 题材键（如 wuxia, xianxia）

        Returns:
            GenericThemeAgent 实例
        """
        if genre_key in self._agents:
            return self._agents[genre_key]

        # 加载配置文件
        config_path = self.config_dir / f"{genre_key}.yaml"

        if not config_path.exists():
            raise ValueError(f"题材配置不存在: {config_path}")

        agent = GenericThemeAgent.from_yaml(str(config_path))
        self._agents[genre_key] = agent

        return agent

    def list_available_genres(self) -> List[str]:
        """列出所有可用题材"""
        return [
            path.stem
            for path in self.config_dir.glob("*.yaml")
        ]

    def preload_all(self):
        """预加载所有题材"""
        for genre_key in self.list_available_genres():
            self.get_agent(genre_key)


# ─── 使用示例 ───

def example_usage():
    """使用示例"""

    # 方式 1：直接从 YAML 加载
    wuxia_agent = GenericThemeAgent.from_yaml(
        "application/engine/theme/configs/wuxia.yaml"
    )

    print(f"题材: {wuxia_agent.genre_name}")
    print(f"人设: {wuxia_agent.get_system_persona()[:50]}...")

    # 方式 2：使用工厂
    factory = ThemeAgentFactory("application/engine/theme/configs")

    for genre in factory.list_available_genres():
        agent = factory.get_agent(genre)
        print(f"- {agent.genre_name} ({agent.genre_key})")


if __name__ == "__main__":
    example_usage()
