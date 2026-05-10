"""CheckpointManager — 应用层Checkpoint管理

核心职责：
- 触发策略：章节完成/幕切换/大纲变更/用户干预
- HEAD指针管理
- 保留策略执行
- 与持久化队列集成（异步落盘）
"""
from engine.application.checkpoint_manager.manager import CheckpointManager

__all__ = ["CheckpointManager"]
