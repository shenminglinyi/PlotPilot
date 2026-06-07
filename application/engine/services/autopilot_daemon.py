"""AutopilotDaemon — 已废弃，请使用 engine.runtime.engine_daemon.EngineDaemon

保留此类仅供旧代码直接 import；新代码与 start_daemon.py 均应使用 EngineDaemon。
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from domain.novel.entities.novel import Novel

from engine.runtime.daemon_host import DaemonHostMixin, init_daemon_dependencies

logger = logging.getLogger(__name__)


class AutopilotDaemon(DaemonHostMixin):
    """已废弃 — 请改用 EngineDaemon"""

    def __init__(
        self,
        novel_repository,
        llm_service,
        context_builder,
        background_task_service,
        planning_service,
        story_node_repo,
        chapter_repository,
        poll_interval: int = 5,
        voice_drift_service=None,
        circuit_breaker=None,
        chapter_workflow: Optional[AutoNovelGenerationWorkflow] = None,
        aftermath_pipeline: Optional[ChapterAftermathPipeline] = None,
        volume_summary_service=None,
        foreshadowing_repository=None,
        knowledge_service=None,
        use_story_pipeline_for_writing: bool = False,
    ):
        warnings.warn(
            "AutopilotDaemon 已废弃，请使用 engine.runtime.engine_daemon.EngineDaemon",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.warning(
            "AutopilotDaemon 已废弃，请迁移至 EngineDaemon（start_daemon.py 已默认使用 EngineDaemon）"
        )
        init_daemon_dependencies(
            self,
            novel_repository=novel_repository,
            llm_service=llm_service,
            context_builder=context_builder,
            background_task_service=background_task_service,
            planning_service=planning_service,
            story_node_repo=story_node_repo,
            chapter_repository=chapter_repository,
            poll_interval=poll_interval,
            voice_drift_service=voice_drift_service,
            circuit_breaker=circuit_breaker,
            chapter_workflow=chapter_workflow,
            aftermath_pipeline=aftermath_pipeline,
            volume_summary_service=volume_summary_service,
            foreshadowing_repository=foreshadowing_repository,
            knowledge_service=knowledge_service,
            use_story_pipeline_for_writing=use_story_pipeline_for_writing,
        )

    def run_forever(self) -> None:
        from engine.runtime.daemon_loop import run_daemon_loop

        banner = (
            f"Autopilot Daemon Started | poll={self.poll_interval}s | "
            f"circuit_breaker={'on' if self.circuit_breaker else 'off'} | "
            f"story_pipeline_writing={'on' if self.use_story_pipeline_for_writing else 'off'}"
        )
        run_daemon_loop(self, banner=banner)

    async def _process_novel(self, novel: Novel) -> None:
        from engine.runtime.novel_lifecycle import process_novel

        await process_novel(self, novel)

    async def _handle_macro_planning(self, novel: Novel) -> None:
        from engine.runtime.macro_planning_delegate import run_macro_planning

        await run_macro_planning(self, novel)

    async def _handle_act_planning(self, novel: Novel) -> None:
        from engine.runtime.act_planning_delegate import run_act_planning

        await run_act_planning(self, novel)

    async def _handle_writing(self, novel: Novel) -> None:
        from engine.runtime.writing_delegate import run_writing

        await run_writing(self, novel)

    async def _handle_auditing(self, novel: Novel) -> None:
        from engine.runtime.audit_delegate import run_chapter_audit

        await run_chapter_audit(self, novel)
