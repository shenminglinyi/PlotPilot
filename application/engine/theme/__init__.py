"""专项题材 Agent 插槽系统

通过 ThemeAgent 抽象接口，为不同题材（玄幻/悬疑/言情/恐怖/科幻等）
提供专项写作能力的注入点，无需修改核心管线逻辑。

核心组件：
- ThemeAgent: 题材 Agent 抽象接口
- ThemeAgentRegistry: 题材 Agent 注册中心
- agents/: 各题材的具体实现
"""

from application.engine.theme.theme_agent import ThemeAgent, BeatTemplate
from application.engine.theme.theme_registry import ThemeAgentRegistry

__all__ = ["ThemeAgent", "BeatTemplate", "ThemeAgentRegistry"]
