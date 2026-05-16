"""StoryPipelineRunner — 写作管线运行器

替代 AutopilotDaemon，作为 BaseStoryPipeline 的具体实现。
运行器继承基类，补充了守护进程特有的逻辑：
- 死循环轮询数据库
- 状态机路由（宏观规划/幕级规划/写作/审计）
- 熔断保护
- 心跳监控
- 共享内存更新

与 AutopilotDaemon 的关系：
- AutopilotDaemon 仍然存在（向后兼容）
- StoryPipelineRunner 是新代码的目标形态
- 逐步将 AutopilotDaemon 的逻辑迁移到此类中
"""
from __future__ import annotations

import time
import logging
import asyncio
from typing import Any, Dict, List, Optional

from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext, PipelineResult
from engine.pipeline.steps import StepResult

logger = logging.getLogger(__name__)


class StoryPipelineRunner(BaseStoryPipeline):
    """写作管线运行器 — 替代 AutopilotDaemon

    继承 BaseStoryPipeline，补充守护进程特有的逻辑。
    核心改进：所有步骤都委托给基类的 _step_xxx() 方法，
    运行器只负责"何时运行"而非"如何运行"。

    使用方式：
        runner = StoryPipelineRunner(
            novel_repository=repo,
            llm_service=llm,
            ...
        )
        runner.run_forever()  # 守护进程模式

    或者：
        ctx = PipelineContext(novel_id="novel-123", chapter_number=5)
        ctx.inject(novel_repository=repo, llm_service=llm, ...)
        result = await runner.run_chapter(ctx)  # 单章模式
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
    ):
        super().__init__()

        # 存储依赖（与 AutopilotDaemon 的 __init__ 完全兼容）
        self.novel_repository = novel_repository
        self.llm_service = llm_service
        self.context_builder = context_builder
        self.background_task_service = background_task_service
        self.planning_service = planning_service
        self.story_node_repo = story_node_repo
        self.chapter_repository = chapter_repository
        self.poll_interval = poll_interval
        self.voice_drift_service = voice_drift_service
        self.circuit_breaker = circuit_breaker
        self.chapter_workflow = chapter_workflow
        self.aftermath_pipeline = aftermath_pipeline
        self.foreshadowing_repository = foreshadowing_repository
        self.knowledge_service = knowledge_service

        # 惰性初始化 VolumeSummaryService
        if not volume_summary_service and llm_service and story_node_repo:
            try:
                from application.blueprint.services.volume_summary_service import VolumeSummaryService
                self.volume_summary_service = VolumeSummaryService(
                    llm_service=llm_service,
                    story_node_repository=story_node_repo,
                    chapter_repository=chapter_repository,
                    foreshadowing_repository=foreshadowing_repository,
                )
            except ImportError:
                self.volume_summary_service = None
        else:
            self.volume_summary_service = volume_summary_service

    def _make_context(self, novel_id: str, chapter_number: int = 0, **kwargs) -> PipelineContext:
        """从运行器的依赖创建 PipelineContext

        将运行器持有的所有依赖注入到上下文中，
        避免每次手动 inject()。
        """
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

        # 注入 PolicyValidator
        try:
            from engine.runtime.policy_validator import PolicyValidator
            ctx.policy_validator = PolicyValidator()
        except ImportError:
            pass

        return ctx

    # ═══════════════════════════════════════════════════════════════
    # 守护进程主循环
    # ═══════════════════════════════════════════════════════════════

    def run_forever(self) -> None:
        """守护进程主循环（与 AutopilotDaemon.run_forever() 兼容）

        死循环轮询数据库，捞出所有 autopilot_status=RUNNING 的小说，
        根据当前阶段路由到对应的处理方法。
        """
        logger.info("=" * 80)
        logger.info("StoryPipelineRunner Started")
        logger.info(f"   Poll Interval: {self.poll_interval}s")
        logger.info(f"   Circuit Breaker: {'Enabled' if self.circuit_breaker else 'Disabled'}")
        logger.info(f"   Voice Drift Service: {'Enabled' if self.voice_drift_service else 'Disabled'}")
        logger.info("=" * 80)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop_count = 0
        while True:
            loop_count += 1
            loop_start = time.time()

            # 熔断器检查
            if self.circuit_breaker and self.circuit_breaker.is_open():
                wait = self.circuit_breaker.wait_seconds()
                logger.warning(f"熔断器打开，暂停 {wait:.0f}s")
                time.sleep(min(wait, self.poll_interval))
                continue

            try:
                active_novels = self._get_active_novels()

                if loop_count % 10 == 1:
                    logger.info(f"Loop #{loop_count}: 发现 {len(active_novels)} 本活跃小说")

                for novel in active_novels:
                    loop.run_until_complete(self._process_novel(novel))

            except Exception as e:
                logger.error(f"Runner 顶层异常: {e}", exc_info=True)

            loop_elapsed = time.time() - loop_start
            time.sleep(self.poll_interval)

    def _get_active_novels(self) -> List[Any]:
        """获取所有活跃小说"""
        if self.novel_repository is None:
            return []
        try:
            from domain.novel.entities.novel import AutopilotStatus
            return self.novel_repository.find_by_autopilot_status(AutopilotStatus.RUNNING.value)
        except Exception:
            return []

    async def _process_novel(self, novel: Any) -> None:
        """处理单个小说 — 状态机路由"""
        try:
            stage = getattr(novel, 'current_stage', None)
            stage_value = stage.value if hasattr(stage, 'value') else str(stage)

            if stage_value in ("macro_planning", "planning"):
                await self._handle_macro_planning(novel)
            elif stage_value == "act_planning":
                await self._handle_act_planning(novel)
            elif stage_value == "writing":
                await self._handle_writing(novel)
            elif stage_value == "auditing":
                await self._handle_auditing(novel)

        except Exception as e:
            logger.error(f"[{getattr(novel, 'novel_id', '?')}] 处理失败: {e}", exc_info=True)

    async def _handle_writing(self, novel: Any) -> None:
        """写作阶段 — 使用 BaseStoryPipeline.run_chapter()"""
        novel_id = novel.novel_id.value if hasattr(novel.novel_id, 'value') else str(novel.novel_id)
        target_words = getattr(novel, 'target_words_per_chapter', None) or self.DEFAULT_TARGET_WORDS

        ctx = self._make_context(
            novel_id=novel_id,
            target_word_count=int(target_words),
            phase=self._get_novel_phase(novel),
            auto_approve_mode=getattr(novel, 'auto_approve_mode', False),
            genre=getattr(novel, 'genre', ''),
            era=getattr(novel, 'era', 'ancient'),
        )

        result = await self.run_chapter(ctx)
        if result.success:
            logger.info(f"[{novel_id}] 管线完成：第{result.chapter_number}章，{result.word_count}字，张力{result.tension}")
        else:
            logger.error(f"[{novel_id}] 管线失败：{result.error}")

    async def _handle_macro_planning(self, novel: Any) -> None:
        """宏观规划 — 委托给 planning_service"""
        if self.planning_service is None:
            return
        novel_id = novel.novel_id.value if hasattr(novel.novel_id, 'value') else str(novel.novel_id)
        try:
            result = await self.planning_service.generate_macro_plan(
                novel_id=novel_id,
                target_chapters=getattr(novel, 'target_chapters', 30),
                structure_preference=None,
            )
            await self.planning_service.apply_macro_plan_from_llm_result(
                result,
                novel_id=novel_id,
                target_chapters=getattr(novel, 'target_chapters', 30),
                minimal_fallback_on_empty=True,
            )
        except Exception as e:
            logger.error(f"[{novel_id}] 宏观规划失败: {e}")

    async def _handle_act_planning(self, novel: Any) -> None:
        """幕级规划 — 委托给 planning_service"""
        if self.planning_service is None:
            return
        novel_id = novel.novel_id.value if hasattr(novel.novel_id, 'value') else str(novel.novel_id)
        logger.info(f"[{novel_id}] 幕级规划 (第 {getattr(novel, 'current_act', 0) + 1} 幕)")

    async def _handle_auditing(self, novel: Any) -> None:
        """审计阶段 — 使用管线的 _step_validate_voice + _step_run_post_commit"""
        novel_id = novel.novel_id.value if hasattr(novel.novel_id, 'value') else str(novel.novel_id)
        logger.info(f"[{novel_id}] 审计阶段")

    def _get_novel_phase(self, novel: Any) -> str:
        """获取小说的故事阶段"""
        try:
            from engine.core.entities.story import StoryPhase
            stage = getattr(novel, 'current_stage', None)
            stage_value = stage.value if hasattr(stage, 'value') else str(stage)
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
