"""StoryPipeline 写作阶段委托

环境变量 PLOTPILOT_USE_STORY_PIPELINE:
  - 未设置（默认）/ writing / 1 / true: StoryPipeline 写作
  - full / all / engine: StoryPipeline 写作（与 writing 等价）
  - off / legacy / false / 0: legacy 节拍写作（紧急回退）

生产入口统一为 EngineDaemon（Phase 9）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Literal

logger = logging.getLogger(__name__)

_ENV_FLAG = "PLOTPILOT_USE_STORY_PIPELINE"
PipelineMode = Literal["off", "writing", "full"]


def get_story_pipeline_mode() -> PipelineMode:
    """解析引擎内核模式（未设置时默认 writing，Phase 4）"""
    val = os.getenv(_ENV_FLAG, "").strip().lower()
    if val in ("off", "legacy", "false", "0", "no"):
        return "off"
    if val in ("full", "all", "engine"):
        return "full"
    if val in ("1", "true", "yes", "on", "writing"):
        return "writing"
    if not val:
        return "writing"
    logger.warning(
        "未知 %s=%r，使用默认 writing；回退 legacy 请设 off",
        _ENV_FLAG,
        os.getenv(_ENV_FLAG),
    )
    return "writing"


def is_story_pipeline_writing_enabled() -> bool:
    """写作阶段是否走新内核（4a 或 4b）"""
    return get_story_pipeline_mode() in ("writing", "full")


def _build_runner(daemon: Any):
    from engine.runtime.runner import StoryPipelineRunner

    return StoryPipelineRunner(
        novel_repository=daemon.novel_repository,
        llm_service=daemon.llm_service,
        context_builder=daemon.context_builder,
        background_task_service=daemon.background_task_service,
        planning_service=daemon.planning_service,
        story_node_repo=daemon.story_node_repo,
        chapter_repository=daemon.chapter_repository,
        poll_interval=daemon.poll_interval,
        voice_drift_service=daemon.voice_drift_service,
        circuit_breaker=daemon.circuit_breaker,
        chapter_workflow=daemon.chapter_workflow,
        aftermath_pipeline=daemon.aftermath_pipeline,
        volume_summary_service=daemon.volume_summary_service,
        foreshadowing_repository=daemon.foreshadowing_repository,
        knowledge_service=daemon.knowledge_service,
    )


async def run_writing(host: Any, novel: Any) -> None:
    """写作阶段统一入口 — 按 host 配置或环境变量选择新/旧管线"""
    if getattr(host, "use_story_pipeline_for_writing", False):
        await run_story_pipeline_writing(host, novel)
        return
    from engine.runtime.legacy_writing_delegate import run_legacy_writing

    await run_legacy_writing(host, novel)


async def run_story_pipeline_writing(daemon: Any, novel: Any) -> None:
    """执行单章写作（新管线），并同步 novel 状态到 daemon 模型"""
    from domain.novel.entities.novel import NovelStage
    from engine.pipelines.registry import get_pipeline_registry

    novel_id = novel.novel_id.value if hasattr(novel.novel_id, "value") else str(novel.novel_id)
    runner = _build_runner(daemon)
    target_words = int(getattr(novel, "target_words_per_chapter", None) or runner.DEFAULT_TARGET_WORDS)
    genre = (getattr(novel, "genre", "") or "").strip().lower()

    logger.info("[%s] StoryPipeline 写作模式 genre=%s", novel_id, genre or "(default)")

    def _writing_sink(substep: str, label: str, extra: Dict[str, Any]) -> None:
        daemon._update_shared_state(
            novel_id,
            writing_substep=substep,
            writing_substep_label=label,
            **extra,
        )

    ctx = runner._make_context(
        novel_id=novel_id,
        target_word_count=target_words,
        phase=runner._get_novel_phase(novel),
        auto_approve_mode=getattr(novel, "auto_approve_mode", False),
        genre=getattr(novel, "genre", ""),
        era=getattr(novel, "era", "ancient"),
    )
    ctx.writing_progress_sink = _writing_sink

    pipeline = get_pipeline_registry().create_pipeline(genre)
    result = await pipeline.run_chapter(ctx)

    if result.success:
        chapter_num = result.chapter_number or ctx.chapter_number
        novel.current_auto_chapters = (novel.current_auto_chapters or 0) + 1
        novel.current_chapter_in_act = (novel.current_chapter_in_act or 0) + 1
        novel.current_beat_index = 0
        novel.beats_completed = False
        if result.tension:
            novel.last_chapter_tension = result.tension
        novel.current_stage = NovelStage.AUDITING

        daemon._update_shared_state(
            novel_id,
            writing_substep="pipeline_done",
            writing_substep_label="写作完成，进入审计",
            current_chapter_number=chapter_num,
            last_chapter_tension=result.tension,
        )
        daemon._flush_novel(novel)
        logger.info(
            "[%s] StoryPipeline 完成：第%s章 %s字 张力%s",
            novel_id,
            chapter_num,
            result.word_count,
            result.tension,
        )
        return

    error = result.error or "unknown"
    if "所有章节已写完" in error:
        logger.info("[%s] StoryPipeline：当前幕章节已全部写完", novel_id)
        if await daemon._current_act_fully_written(novel):
            novel.current_act = (novel.current_act or 0) + 1
            novel.current_chapter_in_act = 0
            novel.current_stage = NovelStage.ACT_PLANNING
            daemon._update_shared_state(
                novel_id,
                current_stage="act_planning",
                writing_substep="act_planning",
                writing_substep_label="幕级规划",
            )
        daemon._flush_novel(novel)
        return

    novel.consecutive_error_count = (getattr(novel, "consecutive_error_count", 0) or 0) + 1
    daemon._flush_novel(novel)
    logger.error("[%s] StoryPipeline 写作失败: %s", novel_id, error)
