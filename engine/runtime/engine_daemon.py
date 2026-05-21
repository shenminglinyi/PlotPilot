"""EngineDaemon — PlotPilot 统一生产入口 (Phase 9)

所有模式均通过 StoryPipelineRunner + DaemonHostMixin 运行；
`use_story_pipeline_for_writing` 控制写作走新管线或 legacy 节拍写作。

环境变量 PLOTPILOT_USE_STORY_PIPELINE:
  - 未设置 / writing / 1: 默认 StoryPipeline 写作
  - full / engine:        StoryPipeline 写作（与 writing 等价）
  - off / legacy:         legacy 节拍写作（紧急回退）
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EngineDaemon:
    """PlotPilot 剧情引擎守护进程 — start_daemon.py 唯一推荐入口"""

    def __init__(self, **daemon_kwargs: Any):
        from engine.runtime.runner import StoryPipelineRunner
        from engine.runtime.writing_delegate import get_story_pipeline_mode

        if "use_story_pipeline_for_writing" not in daemon_kwargs:
            daemon_kwargs["use_story_pipeline_for_writing"] = (
                get_story_pipeline_mode() in ("writing", "full")
            )

        self._use_story_pipeline_for_writing = bool(
            daemon_kwargs.get("use_story_pipeline_for_writing")
        )
        self._runner = StoryPipelineRunner(**daemon_kwargs)

    @property
    def runner(self):
        """StoryPipelineRunner（规划/审计/写作 + DaemonHostMixin）"""
        return self._runner

    @property
    def inner(self):
        """兼容旧代码：inner 即 runner"""
        return self._runner

    @property
    def use_story_pipeline_for_writing(self) -> bool:
        return self._use_story_pipeline_for_writing

    def run_forever(self) -> None:
        writing_mode = "StoryPipeline" if self._use_story_pipeline_for_writing else "legacy"
        logger.info("=" * 80)
        logger.info("EngineDaemon Started (Phase 9)")
        logger.info("  Host: StoryPipelineRunner + DaemonHostMixin")
        logger.info("  写作: %s", writing_mode)
        logger.info("  规划/审计: engine/runtime delegates")
        logger.info("=" * 80)
        self._runner.run_forever()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runner, name)
