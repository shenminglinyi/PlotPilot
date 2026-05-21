"""StoryPipelineRunner — 写作管线运行器

Phase 8: 继承 DaemonHostMixin，作为 full 模式下的自洽守护进程 host。
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext
from engine.runtime.daemon_host import DaemonHostMixin, init_daemon_dependencies

logger = logging.getLogger(__name__)


class StoryPipelineRunner(DaemonHostMixin, BaseStoryPipeline):
    """StoryPipeline 守护进程 — DaemonHostMixin + BaseStoryPipeline

    full 模式下由 EngineDaemon 直接实例化，无需 AutopilotDaemon 过渡层。
    """

    def __init__(
        self,
        novel_repository=None,
        llm_service=None,
        context_builder=None,
        background_task_service=None,
        planning_service=None,
        story_node_repo=None,
        chapter_repository=None,
        poll_interval: int = 5,
        voice_drift_service=None,
        circuit_breaker=None,
        chapter_workflow=None,
        aftermath_pipeline=None,
        volume_summary_service=None,
        foreshadowing_repository=None,
        knowledge_service=None,
        use_story_pipeline_for_writing: bool | None = None,
    ):
        BaseStoryPipeline.__init__(self)
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
        self._legacy_daemon: Any = None

    def attach_legacy_daemon(self, daemon: Any) -> None:
        """可选：绑定 AutopilotDaemon（向后兼容，full 模式不再需要）"""
        self._legacy_daemon = daemon

    @property
    def host(self) -> Any:
        """runtime delegates 使用的 host（优先 legacy，默认 self）"""
        return self._legacy_daemon if self._legacy_daemon is not None else self

    def _make_context(self, novel_id: str, chapter_number: int = 0, **kwargs) -> PipelineContext:
        ctx = PipelineContext(
            novel_id=novel_id,
            chapter_number=chapter_number,
            **kwargs,
        )
        ctx.inject(
            novel_repository=self.novel_repository,
            chapter_repository=self.chapter_repository,
            llm_service=self.llm_service,
            context_builder=self.context_builder,
            aftermath_pipeline=self.aftermath_pipeline,
            voice_drift_service=self.voice_drift_service,
            knowledge_service=self.knowledge_service,
            foreshadowing_repository=self.foreshadowing_repository,
            story_node_repo=self.story_node_repo,
            planning_service=self.planning_service,
            chapter_workflow=self.chapter_workflow,
            background_task_service=self.background_task_service,
            circuit_breaker=self.circuit_breaker,
            volume_summary_service=self.volume_summary_service,
        )

        try:
            from engine.runtime.policy_validator import PolicyValidator

            ctx.policy_validator = PolicyValidator()
        except ImportError:
            pass

        try:
            from infrastructure.persistence.database.connection import get_connection_pool
            from engine.infrastructure.memory.memory_orchestrator_impl import MemoryOrchestratorImpl

            ctx.memory_orchestrator = MemoryOrchestratorImpl(
                db_pool=get_connection_pool(),
                llm_service=self.llm_service,
            )
        except Exception:
            pass

        return ctx

    def run_forever(self) -> None:
        from engine.runtime.daemon_loop import run_daemon_loop

        banner = (
            f"StoryPipelineRunner Started | poll={self.poll_interval}s | "
            f"circuit_breaker={'on' if self.circuit_breaker else 'off'} | "
            f"story_pipeline={'on' if self.use_story_pipeline_for_writing else 'off'}"
        )
        run_daemon_loop(self, banner=banner)

    async def _process_novel(self, novel: Any) -> None:
        from engine.runtime.novel_lifecycle import process_novel

        await process_novel(self.host, novel)

    async def _handle_macro_planning(self, novel: Any) -> None:
        from engine.runtime.macro_planning_delegate import run_macro_planning

        await run_macro_planning(self.host, novel)

    async def _handle_act_planning(self, novel: Any) -> None:
        from engine.runtime.act_planning_delegate import run_act_planning

        await run_act_planning(self.host, novel)

    async def _handle_writing(self, novel: Any) -> None:
        from engine.runtime.writing_delegate import run_writing

        await run_writing(self.host, novel)

    async def _handle_auditing(self, novel: Any) -> None:
        from engine.runtime.audit_delegate import run_chapter_audit

        await run_chapter_audit(self.host, novel)

    def _get_novel_phase(self, novel: Any) -> str:
        try:
            stage = getattr(novel, "current_stage", None)
            stage_value = stage.value if hasattr(stage, "value") else str(stage)
            phase_map = {
                "macro_planning": "opening",
                "act_planning": "opening",
                "writing": "development",
                "auditing": "development",
                "paused_for_review": "development",
                "completed": "finale",
            }
            return phase_map.get(stage_value, "opening")
        except Exception:
            return "opening"
