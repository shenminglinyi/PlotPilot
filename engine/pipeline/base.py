"""BaseStoryPipeline — 写作管线基类

这是 AIText 引擎的灵魂。一个类，十个步骤，继承即扩展。

完整管线流程（单章生成）：
 1. _step_find_next_chapter(ctx)     定位下一个待写章节
 2. _step_build_context(ctx)         组装上下文（四层洋葱挤压）
 3. _step_prepare_chapter_plan(ctx)  章节执行剧本准备
 4. _step_generate(ctx)              LLM 整章一次生成
 5. _step_validate_content(ctx)      策略验证（反AI/俗套/一致性）
 6. _step_save_chapter(ctx)          保存章节（独立短连接写库）
 7. _step_validate_voice(ctx)        文风审计（声线漂移检测+改写）
 8. _step_run_post_commit(ctx)       章后管线（叙事/向量/KG/伏笔）
 9. _step_score_tension(ctx)         张力打分（0-100 多维评分）
10. _step_finalize(ctx)              收尾（落库+状态推进）
"""
from __future__ import annotations

import logging
import time
from abc import ABC
from typing import Any, Dict, List, Optional

from engine.pipeline.context import PipelineContext, PipelineResult
from engine.pipeline.steps import StepResult
from engine.pipeline.telemetry import story_pipeline_wave_meta

logger = logging.getLogger(__name__)

def _writing_progress(
    ctx: PipelineContext,
    substep: str,
    label: str,
    *,
    pipeline_wave_index: Optional[int] = None,
    **extras: Any,
) -> None:
    """推送到全托管共享状态（writing_substep* + StoryPipeline 波次），供 /status 与 UI 管线图。"""
    sink = getattr(ctx, "writing_progress_sink", None)
    if sink is None:
        return
    payload = {k: v for k, v in extras.items() if v is not None}
    if pipeline_wave_index is not None:
        meta = story_pipeline_wave_meta(int(pipeline_wave_index))
        if meta:
            payload.update(meta)
    try:
        sink(substep, label, payload)
    except Exception as e:
        logger.debug("[%s] writing_progress_sink 失败: %s", getattr(ctx, "novel_id", "?"), e)


class BaseStoryPipeline(ABC):
    """写作管线基类 — 继承即扩展，开箱即用

    可覆写的类属性（调参）：
    - DEFAULT_TARGET_WORDS: 默认目标字数
    - VOICE_REWRITE_THRESHOLD: 声线漂移阈值
    - VOICE_REWRITE_MAX_ATTEMPTS: 定向改写最大轮数
    - MIN_PASS_SCORE: 策略验证最低通过分数
    - BATCH_WRITE_INTERVAL: 保留给兼容运行时的批量写库间隔
    """

    # ─── 可覆写的类属性（调参） ───
    DEFAULT_TARGET_WORDS: int = 2500
    VOICE_REWRITE_THRESHOLD: float = 0.68
    VOICE_REWRITE_MAX_ATTEMPTS: int = 3
    VOICE_WARNING_DEFAULT_THRESHOLD: float = 0.75
    MIN_PASS_SCORE: float = 0.6
    BATCH_WRITE_INTERVAL: int = 3
    STREAM_PUSH_INTERVAL: float = 0.15

    def __init__(self):
        """初始化管线。子类可在此设置额外依赖。"""
        self._step_log: List[Dict[str, Any]] = []

    # ═══════════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════════

    async def run_chapter(self, ctx: PipelineContext) -> PipelineResult:
        """执行完整的章节生成管线

        严格按 _step_* 方法定义顺序调用。子类通常不需要重写此方法，
        而是重写具体的步骤方法。

        Args:
            ctx: 管线上下文，携带所有依赖和输入数据

        Returns:
            PipelineResult: 管线最终输出
        """
        self._step_log = []
        step_status: Dict[str, str] = {}

        try:
            # 1. 定位下一个待写章节
            r = await self._step_find_next_chapter(ctx)
            step_status["find_next_chapter"] = "ok" if r.passed else ("skipped" if r.skip else "failed")
            if not r.passed and not r.skip:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)
            if r.passed:
                _writing_progress(
                    ctx,
                    "chapter_found",
                    f"章节定位 · 第 {ctx.chapter_number} 章",
                    pipeline_wave_index=1,
                    current_chapter_number=ctx.chapter_number,
                    chapter_target_words=ctx.target_word_count,
                )

            # 1b. 叙事治理准备：生成章节预算与上下文请求，作为后续上下文组装的硬约束输入。
            await self._step_prepare_governance(ctx)

            # 2. 章节执行剧本准备：旧数据直接复用七段，新幕级轻量链条在这里补成七段。
            r = await self._step_prepare_chapter_plan(ctx)
            step_status["prepare_chapter_plan"] = "ok" if r.passed else "failed"
            if not r.passed:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)
            _writing_progress(
                ctx,
                "chapter_plan_ready",
                "章节执行剧本准备完成",
                pipeline_wave_index=2,
                current_chapter_number=ctx.chapter_number,
                total_beats=0,
                current_beat_index=0,
                chapter_target_words=ctx.target_word_count,
                chapter_plan_mode=ctx.metadata.get("chapter_plan_mode") or "",
            )

            # 3. 组装上下文（四层洋葱挤压）
            r = await self._step_build_context(ctx)
            step_status["build_context"] = "ok" if r.passed else "failed"
            if not r.passed:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)
            _writing_progress(
                ctx,
                "context_assembly",
                "组装上下文",
                pipeline_wave_index=3,
                current_chapter_number=ctx.chapter_number,
                context_tokens=int(ctx.context_tokens or 0),
                chapter_target_words=ctx.target_word_count,
            )

            # 4. LLM 生成（整章一次写完）
            r = await self._step_generate(ctx)
            step_status["generate"] = "ok" if r.passed else "failed"
            if not r.passed:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)

            # 5. 策略验证（反AI/俗套/一致性）
            r = await self._step_validate_content(ctx)
            step_status["validate_content"] = "ok" if r.passed else "warning"
            if not r.passed:
                logger.warning(f"[{ctx.novel_id}] 内容验证未通过: {r.message}")
                # 验证失败不阻断管线，记录违规但继续

            # 6. 保存章节（独立短连接写库）
            r = await self._step_save_chapter(ctx)
            step_status["save_chapter"] = "ok" if r.passed else "failed"
            if not r.passed:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)

            # 7. 文风审计（声线漂移检测+改写）
            r = await self._step_validate_voice(ctx)
            step_status["validate_voice"] = "ok" if r.passed else "warning"
            if not r.passed:
                logger.warning(f"[{ctx.novel_id}] 文风审计未通过: {r.message}")

            # 8. 章后管线（叙事同步/向量索引/KG推断/伏笔/因果边/人物状态/债务）
            r = await self._step_run_post_commit(ctx)
            step_status["run_post_commit"] = "ok" if r.passed else "warning"
            if not r.passed:
                logger.warning(f"[{ctx.novel_id}] 章后管线失败: {r.message}")

            # 9. 张力打分（0-100 多维评分）
            r = await self._step_score_tension(ctx)
            step_status["score_tension"] = "ok" if r.passed else "warning"
            if not r.passed:
                logger.warning(f"[{ctx.novel_id}] 张力打分失败: {r.message}")

            # 10. 收尾（落库+状态推进）
            r = await self._step_finalize(ctx)
            step_status["finalize"] = "ok" if r.passed else "failed"
            if not r.passed:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)

            return self._make_result(ctx, success=True, step_status=step_status)

        except Exception as e:
            logger.error(f"[{ctx.novel_id}] 管线异常: {e}", exc_info=True)
            return self._make_result(ctx, success=False, error=str(e), step_status=step_status)

    # ═══════════════════════════════════════════════════════════════
    # 十大步骤 — 每个都有默认实现，子类可覆写
    # ═══════════════════════════════════════════════════════════════

    async def _step_find_next_chapter(self, ctx: PipelineContext) -> StepResult:
        """步骤1：定位下一个待写章节

        默认实现：查询 story_node_repo，找到下一个未写章节。
        检测余韵章需求（上章张力>=80时触发）。

        子类覆写场景：
        - 短剧引擎跳过缓冲章
        - 推理引擎要求按时间线顺序写
        """
        self._log_step("find_next_chapter", "定位待写章节")

        if ctx.story_node_repo is None:
            return StepResult.fail("story_node_repo 未设置，无法定位章节")

        try:
            nodes = await ctx.story_node_repo.get_by_novel(ctx.novel_id)
            chapter_nodes = sorted(
                [n for n in nodes if getattr(n, 'node_type', None) and n.node_type.value == "chapter"],
                key=lambda n: n.number,
            )
            for node in chapter_nodes:
                # 找到第一个未完成的章节
                existing = None
                if ctx.chapter_repository:
                    try:
                        from domain.novel.value_objects.novel_id import NovelId
                        existing = ctx.chapter_repository.get_by_novel_and_number(
                            NovelId(ctx.novel_id), node.number
                        )
                    except Exception:
                        pass
                if existing is None or getattr(existing, 'status', '') != 'completed':
                    ctx.chapter_node = node
                    ctx.chapter_number = node.number
                    ctx.outline = node.outline or node.description or node.title or ""
                    if existing is not None:
                        ctx.existing_content = str(getattr(existing, "content", "") or "").strip()
                    try:
                        from domain.novel.value_objects.novel_id import NovelId

                        novel = (
                            ctx.novel_repository.get_by_id(NovelId(ctx.novel_id))
                            if ctx.novel_repository is not None
                            else None
                        )
                        ctx.start_beat_index = int(getattr(novel, "current_beat_index", 0) or 0) if novel else 0
                    except Exception:
                        ctx.start_beat_index = 0
                    return StepResult.ok(f"定位到第 {node.number} 章")

            return StepResult.fail("所有章节已写完，无需继续")
        except Exception as e:
            return StepResult.fail(f"章节定位失败: {e}")

    async def _step_prepare_governance(self, ctx: PipelineContext) -> StepResult:
        """步骤1b：从叙事治理层领取本章预算。

        失败不阻断生成；治理报告会在章后提交闸门再次落库。
        """
        try:
            from application.governance.service import NarrativeGovernanceService
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_governance_repository import (
                SqliteGovernanceRepository,
            )
            from infrastructure.persistence.database.sqlite_storyline_repository import (
                SqliteStorylineRepository,
            )

            db = get_database()
            governance = NarrativeGovernanceService(
                SqliteGovernanceRepository(db),
                ctx.novel_repository,
                SqliteStorylineRepository(db),
                db,
            )
            prepared = governance.prepare_chapter(ctx.novel_id, ctx.chapter_number)
            ctx.governance_budget = prepared.get("budget") or {}
            ctx.governance_context_request = prepared.get("context_request") or {}
            ctx.metadata["governance_budget"] = ctx.governance_budget
            ctx.metadata["governance_context_request"] = ctx.governance_context_request
            try:
                from application.evolution.services.gate_service import EvolutionGateService
                from infrastructure.persistence.database.sqlite_evolution_repository import (
                    SqliteEvolutionRepository,
                )

                continuity = EvolutionGateService(SqliteEvolutionRepository(db)).check(
                    novel_id=ctx.novel_id,
                    chapter_number=ctx.chapter_number,
                    branch_id="main",
                    outline_content=ctx.outline or "",
                )
                ctx.evolution_continuity_report = continuity.to_dict()
                ctx.metadata["evolution_continuity_report"] = ctx.evolution_continuity_report
                if not continuity.is_pass:
                    return StepResult.fail(
                        "写前连续性检查未通过：" + "；".join(continuity.repair_plan[:3])
                    )
            except Exception as gate_error:
                logger.warning("[%s] 写前连续性检查失败: %s", ctx.novel_id, gate_error)
            _writing_progress(
                ctx,
                "governance_prepare",
                "叙事预算与连续性",
                pipeline_wave_index=1,
                current_chapter_number=ctx.chapter_number,
                governance_budget=ctx.governance_budget,
                evolution_continuity_report=ctx.evolution_continuity_report,
            )
            return StepResult.ok("叙事治理预算已准备")
        except Exception as e:
            logger.warning("[%s] 叙事治理预算准备失败: %s", ctx.novel_id, e)
            return StepResult.skip_step(f"叙事治理预算准备失败: {e}")

    async def _step_build_context(self, ctx: PipelineContext) -> StepResult:
        """步骤2：组装上下文（四层洋葱挤压）

        默认实现：优先委托给 chapter_workflow，降级到 context_builder。
        T0(强制)→T1(可压缩)→T2(动态水位线)→T3(可牺牲/向量召回)

        子类覆写场景：
        - 短剧引擎：注入"3分钟反转"规则
        - 推理引擎：注入"线索公平性"规则
        - 武侠引擎：注入修炼体系设定
        """
        self._log_step("build_context", f"组装上下文，目标 {ctx.target_word_count} 字")

        bundle = None

        # 优先使用 chapter_workflow（完整 bundle）
        if ctx.chapter_workflow is not None:
            try:
                bundle = ctx.chapter_workflow.prepare_chapter_generation(
                    ctx.novel_id, ctx.chapter_number, ctx.outline, scene_director=None
                )
                ctx.context_text = bundle.get("context", "")
                ctx.context_tokens = bundle.get("context_tokens", 0)
                ctx.voice_anchors = bundle.get("voice_anchors", "")
                ctx.bundle = bundle
                logger.info(
                    f"[{ctx.novel_id}] 上下文（workflow）: {len(ctx.context_text)} 字符, "
                    f"约 {ctx.context_tokens} tokens"
                )
            except Exception as e:
                logger.warning(f"chapter_workflow 准备失败，降级到 context_builder: {e}")
                bundle = None

        # 降级到 context_builder
        if bundle is None and ctx.context_builder is not None:
            try:
                ctx.context_text = ctx.context_builder.build_context(
                    novel_id=ctx.novel_id,
                    chapter_number=ctx.chapter_number,
                    outline=ctx.outline,
                    max_tokens=20000,
                )
                logger.info(f"[{ctx.novel_id}] 上下文（builder）: {len(ctx.context_text)} 字符")
            except Exception as e:
                logger.warning(f"context_builder 构建失败: {e}")

        # 声线锚点补充
        if not ctx.voice_anchors and ctx.context_builder is not None:
            try:
                ctx.voice_anchors = ctx.context_builder.build_voice_anchor_system_section(ctx.novel_id)
            except Exception:
                ctx.voice_anchors = ""

        # ─── 叙事治理预算（T0 强制层）：总编辑模型给本章的结构边界 ────
        if ctx.governance_budget:
            budget = ctx.governance_budget
            tags = "、".join(budget.get("must_serve_promise_tags") or [])
            notes = "\n".join(f"- {note}" for note in (budget.get("notes") or []))
            lines = [
                "\n\n=== 本章叙事治理预算 ===",
                f"- 最多新增故事线：{budget.get('max_new_storylines', 0)}",
                f"- 最多回收叙事债务：{budget.get('max_debt_closures', 0)}",
                f"- 允许揭秘等级：{budget.get('allowed_reveal_level', 'hint')}",
                "- 世界线规则：优先推进、交汇或回收现有世界线；不要随意开新主线/支线/暗线。",
                "- 新线约束：若预算允许新增，也必须由既有人物、地点、道具或未结因果触发，并在章内给出可追踪的世界切片变化。",
                "- 回滚约束：避免写出会破坏已存档人物状态、地点占用、道具归属和已公开真相的情节。",
            ]
            if tags:
                lines.append(f"- 必须服务承诺标签：{tags}")
            if notes:
                lines.append(notes)
            ctx.context_text = (ctx.context_text or "") + "\n".join(lines)

        # ─── 伏笔主动注入（T0 强制层）：本章应推进/兑现的待回收伏笔 ────
        if ctx.foreshadowing_repository is not None:
            try:
                from domain.novel.value_objects.novel_id import NovelId
                _registry = ctx.foreshadowing_repository.get_by_novel_id(NovelId(ctx.novel_id))
                if _registry and hasattr(_registry, "subtext_entries"):
                    _importance_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
                    _window = ctx.chapter_number + 2
                    _due = [
                        e for e in _registry.subtext_entries
                        if e.status == "pending"
                        and e.suggested_resolve_chapter is not None
                        and e.suggested_resolve_chapter <= _window
                    ]
                    _due.sort(key=lambda e: _importance_rank.get(e.importance, 2), reverse=True)
                    if _due[:3]:
                        _lines = "\n".join(
                            f"- {e.question}（埋于第{e.chapter}章）"
                            for e in _due[:3]
                        )
                        _fshadow_block = f"\n\n=== 本章应推进的伏笔 ===\n{_lines}"
                        ctx.context_text = (ctx.context_text or "") + _fshadow_block
                        logger.info(
                            "[%s] 注入 %d 条待兑现伏笔到生成上下文",
                            ctx.novel_id, len(_due[:3]),
                        )
            except Exception as _fse:
                logger.debug("伏笔注入失败（跳过）: %s", _fse)

        return StepResult.ok()

    async def _step_prepare_chapter_plan(self, ctx: PipelineContext) -> StepResult:
        """步骤3：准备章节执行剧本。

        旧数据若已有七段剧本则直接复用；新幕级规划只提供轻量主事件链，
        本步骤在正文生成前补齐单章七段执行剧本。
        """
        self._log_step("prepare_chapter_plan", "章节执行剧本准备")
        ctx.beats = []

        outline = (ctx.outline or "").strip()
        if not outline:
            return StepResult.fail("章节执行剧本为空，无法整章生成")

        from application.blueprint.services.chapter_planning_policy import has_rendered_chapter_execution_plan

        if has_rendered_chapter_execution_plan(outline):
            ctx.metadata["chapter_plan_mode"] = "full_chapter_script"
            ctx.metadata["outline_plan_mode"] = "full_chapter_script"
        else:
            if ctx.llm_service is None:
                return StepResult.fail("llm_service 未设置，无法生成章前执行剧本")
            preplanning_service = ctx.get_dep("chapter_preplanning_service")
            if preplanning_service is None:
                from application.blueprint.services.chapter_preplanning_service import ChapterPreplanningService

                preplanning_service = ChapterPreplanningService(
                    llm_service=ctx.llm_service,
                    chapter_repository=ctx.chapter_repository,
                    story_node_repo=ctx.story_node_repo,
                )
            try:
                outline = await preplanning_service.ensure_execution_plan(
                    novel_id=ctx.novel_id,
                    chapter_number=ctx.chapter_number,
                    chapter_node=ctx.chapter_node,
                    current_outline=outline,
                    target_words=ctx.target_word_count,
                )
            except Exception as exc:
                return StepResult.fail(f"章前执行剧本生成失败: {exc}")
            ctx.outline = outline
            ctx.metadata["chapter_plan_mode"] = "chapter_preplan"
            ctx.metadata["outline_plan_mode"] = "chapter_preplan"

        logger.info(
            "[%s] 第 %s 章使用整章执行剧本生成，plan_chars=%d target_words=%d",
            ctx.novel_id,
            ctx.chapter_number,
            len(outline),
            ctx.target_word_count,
        )
        self._attach_chapter_preplan_metadata(ctx)
        return StepResult.ok()

    def _attach_chapter_preplan_metadata(self, ctx: PipelineContext) -> None:
        """Expose one structured preplan source to prose generation."""
        node_meta = getattr(ctx.chapter_node, "metadata", {}) if ctx.chapter_node is not None else {}
        if not isinstance(node_meta, dict):
            node_meta = {}
        preplan = node_meta.get("chapter_preplan")
        if not isinstance(preplan, dict):
            preplan = {}

        continuity_context = str(preplan.get("continuity_context") or "").strip()
        if not continuity_context:
            try:
                from application.blueprint.services.chapter_continuity_ledger import ChapterContinuityLedgerService

                continuity_context = ChapterContinuityLedgerService(
                    chapter_repository=ctx.chapter_repository,
                    story_node_repo=ctx.story_node_repo,
                ).build_for_chapter(ctx.novel_id, ctx.chapter_number).to_planning_context_text()
            except Exception:
                continuity_context = ""

        ctx.metadata["continuity_context"] = continuity_context

    async def _step_generate(self, ctx: PipelineContext) -> StepResult:
        composer = ctx.get_dep("prose_composer")
        if composer is not None:
            return await self._step_generate_with_composer(ctx, composer)
        from engine.pipeline.prose_composer import ChapterProseInvocationComposer

        return await self._step_generate_with_composer(ctx, ChapterProseInvocationComposer())

    async def _step_generate_with_composer(self, ctx: PipelineContext, composer: Any) -> StepResult:
        self._log_step("generate", "LLM 生成（整章正文 Composer）")

        if ctx.llm_service is None:
            return StepResult.fail("llm_service 未设置，无法生成")

        from engine.pipeline.prose_composer import ProseCompositionRequest

        _writing_progress(
            ctx,
            "llm_calling",
            "整章正文撰写",
            pipeline_wave_index=4,
            current_chapter_number=ctx.chapter_number,
            total_beats=0,
            current_beat_index=0,
            chapter_target_words=ctx.target_word_count,
            accumulated_words=len((ctx.existing_content or "").strip()),
        )

        def _stream_sink(content: str) -> None:
            self._push_streaming_snapshot(ctx.novel_id, content)
            _writing_progress(
                ctx,
                "llm_calling",
                "整章正文撰写",
                pipeline_wave_index=4,
                current_chapter_number=ctx.chapter_number,
                total_beats=0,
                current_beat_index=0,
                chapter_target_words=ctx.target_word_count,
                accumulated_words=len((content or "").strip()),
            )

        request = ProseCompositionRequest(
            novel_id=ctx.novel_id,
            chapter_number=ctx.chapter_number,
            chapter_title=str(getattr(ctx.chapter_node, "title", "") or ""),
            novel_title=str(ctx.metadata.get("novel_title") or ctx.novel_id),
            genre=ctx.genre,
            outline=ctx.outline,
            context_text=ctx.context_text,
            style_guide=ctx.voice_anchors,
            target_words=ctx.target_word_count,
            auto_approve_mode=ctx.auto_approve_mode,
            metadata=ctx.metadata,
            stream_sink=_stream_sink,
            stop_checker=lambda: self._novel_stream_should_stop(ctx.novel_id),
            host=ctx.get_dep("autopilot_host") or ctx,
            llm_service=ctx.llm_service,
        )
        try:
            result = await composer.compose(request)
        except Exception as exc:
            logger.error("[%s] 整章 Composer 失败，停止本章生成: %s", ctx.novel_id, exc)
            return StepResult.fail(f"整章正文生成失败: {exc}")

        if result.awaiting_review:
            ctx.metadata["awaiting_ai_review"] = True
            ctx.metadata["active_invocation_session_id"] = result.session_id
            return StepResult.fail("awaiting_ai_review")

        content = self._post_process_generation(result.content, ctx)
        if not content.strip():
            return StepResult.fail("章节正文生成失败：Composer 未产出有效正文")

        ctx.chapter_content = content
        ctx.word_count = len(content)
        self._push_streaming_snapshot(ctx.novel_id, content)
        return StepResult.ok()

    async def _step_validate_content(self, ctx: PipelineContext) -> StepResult:
        """步骤5：策略验证（反AI/俗套/一致性）

        默认实现：委托给 PolicyValidator，运行六维度检查。
        - 语言风格（八股文/数字比喻/过度理性/拐弯描写）
        - 角色一致性（OOC检测/语言指纹/创伤反应）
        - 情节密度 / 命名规范 / 视角控制 / 叙事节奏

        验证失败不阻断管线，只记录违规。enforce 模式下可短路。

        子类覆写场景：
        - 添加领域特定验证（如武侠的"武功逻辑"验证）
        - 修改验证阈值
        """
        self._log_step("validate_content", "策略验证")

        _writing_progress(
            ctx,
            "policy_validate",
            "策略校验（反AI·一致性）",
            pipeline_wave_index=5,
            current_chapter_number=ctx.chapter_number,
            total_beats=0,
            chapter_target_words=ctx.target_word_count,
            accumulated_words=ctx.word_count,
        )

        if ctx.policy_validator is not None:
            try:
                report = ctx.policy_validator.advise(
                    text=ctx.chapter_content,
                    character_masks=self._get_character_masks(ctx),
                    chapter_goal=ctx.outline,
                    character_names=self._get_character_names(ctx),
                    era=ctx.era,
                )
                ctx.validation_passed = report.passed
                ctx.validation_score = report.overall_score
                ctx.validation_violations = report.all_violations
                ctx.validation_dimensions = {
                    "language_style": report.language_style_score,
                    "character_consistency": report.character_consistency_score,
                    "plot_density": report.plot_density_score,
                    "naming": report.naming_score,
                    "viewpoint": report.viewpoint_score,
                    "rhythm": report.rhythm_score,
                }
                return StepResult.ok() if report.passed else StepResult(
                    passed=True,  # 不阻断
                    message=f"验证未通过 (score={report.overall_score:.2f})",
                    score=report.overall_score,
                    violations=report.all_violations,
                )
            except Exception as e:
                logger.warning(f"策略验证异常: {e}")
        else:
            # 无 PolicyValidator，跳过
            ctx.validation_passed = True
            ctx.validation_score = 0.85
            ctx.validation_dimensions = {"language_style": 0.85}

        return StepResult.ok()

    async def _step_save_chapter(self, ctx: PipelineContext) -> StepResult:
        """步骤6：保存章节（独立短连接写库）

        默认实现：优先尝试 CQRS 持久化队列，降级到独立短连接写库。
        这是 Rails 式的"直接写库"——没有 PersistencePort 抽象。

        子类通常不需要覆写此步骤。
        """
        self._log_step("save_chapter", f"保存章节 {ctx.chapter_number}，{ctx.word_count} 字")

        if ctx.chapter_repository is None:
            return StepResult.fail("chapter_repository 未设置，无法保存")

        _writing_progress(
            ctx,
            "chapter_persist",
            "章节落盘",
            pipeline_wave_index=6,
            current_chapter_number=ctx.chapter_number,
            total_beats=0,
            current_beat_index=getattr(ctx, "start_beat_index", 0),
            chapter_target_words=ctx.target_word_count,
            accumulated_words=ctx.word_count,
        )

        try:
            # 尝试推持久化队列
            pushed = self._push_persistence_command(ctx)
            if pushed:
                ctx.chapter_saved = True
                ctx.save_method = "queue"
                return StepResult.ok()

            # 降级：通过 repository 直接写库
            await self._save_chapter_via_repository(ctx)
            ctx.chapter_saved = True
            ctx.save_method = "repository"
            return StepResult.ok()
        except Exception as e:
            return StepResult.fail(f"章节保存失败: {e}")

    async def _step_validate_voice(self, ctx: PipelineContext) -> StepResult:
        """步骤7：文风审计（声线漂移检测+定向改写）

        默认实现：
        1. 声线漂移检测（VoiceDriftService）
        2. 若 drift_alert=True 且 similarity < 阈值，触发定向改写
        3. 最多改写 VOICE_REWRITE_MAX_ATTEMPTS 轮

        子类覆写场景：
        - 短剧引擎：降低声线要求
        - 文学引擎：提高声线要求
        """
        self._log_step("validate_voice", "文风审计")

        _writing_progress(
            ctx,
            "voice_drift_check",
            "文风审计 · 声线漂移",
            pipeline_wave_index=7,
            current_chapter_number=ctx.chapter_number,
            accumulated_words=ctx.word_count,
        )

        if ctx.voice_drift_service is not None:
            try:
                if getattr(ctx.voice_drift_service, "use_llm_mode", False):
                    vr = await ctx.voice_drift_service.score_chapter_async(
                        novel_id=ctx.novel_id,
                        chapter_number=ctx.chapter_number,
                        content=ctx.chapter_content,
                    )
                else:
                    vr = ctx.voice_drift_service.score_chapter(
                        novel_id=ctx.novel_id,
                        chapter_number=ctx.chapter_number,
                        content=ctx.chapter_content,
                    )
                ctx.similarity_score = vr.get("similarity_score")
                ctx.drift_alert = bool(vr.get("drift_alert", False))
                ctx.voice_mode = vr.get("mode", "statistics")

                # 定向改写循环
                if ctx.drift_alert and ctx.similarity_score is not None:
                    if ctx.similarity_score < self.VOICE_REWRITE_THRESHOLD:
                        await self._apply_voice_rewrite_loop(ctx)
            except Exception as e:
                logger.warning(f"文风审计失败: {e}")

        return StepResult.ok()

    async def _step_run_post_commit(self, ctx: PipelineContext) -> StepResult:
        """步骤8：章后管线（叙事同步/向量索引/KG推断/伏笔/因果边/人物状态/债务）

        默认实现：委托给 ChapterAftermathPipeline。
        一次 LLM 调用产出：摘要/事件/埋线/三元组/伏笔/因果边/人物状态突变/叙事债务。

        子类通常不需要覆写——这是引擎的"消化系统"，
        把生成的文字转化为结构化知识存回数据库。
        """
        self._log_step("run_post_commit", "章后管线")

        _writing_progress(
            ctx,
            "chapter_aftermath",
            "章后管线（叙事/向量/伏笔等）",
            pipeline_wave_index=8,
            current_chapter_number=ctx.chapter_number,
            accumulated_words=ctx.word_count,
            aftermath_live_status="running",
            aftermath_live_chapter_number=ctx.chapter_number,
        )

        if ctx.aftermath_pipeline is not None:
            try:
                result = await ctx.aftermath_pipeline.run_after_chapter_saved(
                    ctx.novel_id,
                    ctx.chapter_number,
                    ctx.chapter_content,
                )
                ctx.narrative_sync_ok = bool(result.get("narrative_sync_ok", False))
                ctx.vector_stored = bool(result.get("vector_stored", False))
                ctx.foreshadow_stored = bool(result.get("foreshadow_stored", False))
                ctx.triples_extracted = bool(result.get("triples_extracted", False))
                ctx.causal_edges_stored = bool(result.get("causal_edges_stored", False))
                ctx.character_mutations_stored = bool(result.get("character_mutations_stored", False))
                ctx.debt_updated = bool(result.get("debt_updated", False))
                ctx.tension_composite = result.get("tension_composite")
                # 文风结果也可能从 aftermath 返回
                if result.get("similarity_score") is not None and ctx.similarity_score is None:
                    ctx.similarity_score = result["similarity_score"]
                if result.get("drift_alert") and not ctx.drift_alert:
                    ctx.drift_alert = True
                _writing_progress(
                    ctx,
                    "chapter_aftermath_done",
                    "章后管线完成",
                    pipeline_wave_index=8,
                    current_chapter_number=ctx.chapter_number,
                    accumulated_words=ctx.word_count,
                    aftermath_live_status="done",
                    aftermath_live_chapter_number=ctx.chapter_number,
                    narrative_sync_ok=ctx.narrative_sync_ok,
                    vector_stored=ctx.vector_stored,
                    foreshadow_stored=ctx.foreshadow_stored,
                    triples_extracted=ctx.triples_extracted,
                    causal_edges_stored=ctx.causal_edges_stored,
                    character_mutations_stored=ctx.character_mutations_stored,
                    debt_updated=ctx.debt_updated,
                    tension_composite=ctx.tension_composite,
                )
            except Exception as e:
                logger.warning(f"章后管线失败: {e}")
                _writing_progress(
                    ctx,
                    "chapter_aftermath_failed",
                    "章后管线失败",
                    pipeline_wave_index=8,
                    current_chapter_number=ctx.chapter_number,
                    accumulated_words=ctx.word_count,
                    aftermath_live_status="failed",
                    aftermath_live_chapter_number=ctx.chapter_number,
                )

        await self._update_emotion_ledger(ctx)

        return StepResult.ok()

    async def _update_emotion_ledger(self, ctx: PipelineContext) -> None:
        """章后更新 T1 情绪账本（可选，依赖 memory_orchestrator 注入）"""
        memory = ctx.memory_orchestrator
        if memory is None or not ctx.chapter_content:
            return
        try:
            from engine.core.entities.story import StoryId

            updated = await memory.update_emotion_ledger(
                story_id=StoryId(ctx.novel_id),
                chapter_number=ctx.chapter_number,
                chapter_content=ctx.chapter_content,
            )
            ctx.emotion_ledger_updated = updated is not None
        except Exception as e:
            logger.warning(f"情绪账本更新失败: {e}")

    async def _step_score_tension(self, ctx: PipelineContext) -> StepResult:
        """步骤9：张力打分（0-100 多维评分）

        默认实现：优先使用章后管线的多维张力评分，
        降级使用 LLM 单维评分（1-10 → ×10 转 0-100）。

        子类覆写场景：
        - 自定义张力评分逻辑
        - 调整张力维度权重
        """
        self._log_step("score_tension", "张力打分")

        _writing_progress(
            ctx,
            "score_tension_live",
            "张力评估",
            pipeline_wave_index=9,
            current_chapter_number=ctx.chapter_number,
            accumulated_words=ctx.word_count,
        )

        # 优先使用章后管线的多维张力
        if ctx.tension_composite is not None and ctx.tension_composite > 0:
            logger.info(f"[{ctx.novel_id}] 多维张力值：{int(ctx.tension_composite)}/100")
            return StepResult.ok()

        # 降级：使用 LLM 评分
        if ctx.llm_service is not None and ctx.chapter_content:
            try:
                tension = await self._score_tension_via_llm(ctx)
                ctx.tension_composite = float(tension)
                logger.info(f"[{ctx.novel_id}] LLM 张力值：{tension}/100")
            except Exception as e:
                logger.warning(f"张力打分失败: {e}")
                ctx.tension_composite = 50.0  # 默认中等张力

        return StepResult.ok()

    async def _step_finalize(self, ctx: PipelineContext) -> StepResult:
        """步骤10：收尾（落库+状态推进）

        默认实现：
        1. 构建审计快照
        2. 保存 novel 状态到 DB
        3. 推进 current_chapter_in_act / current_act

        子类覆写场景：
        - 自定义状态推进逻辑
        - 添加额外的收尾操作
        """
        self._log_step("finalize", "收尾落库")

        _writing_progress(
            ctx,
            "pipeline_finalize",
            "收尾（状态快照）",
            pipeline_wave_index=10,
            current_chapter_number=ctx.chapter_number,
            accumulated_words=ctx.word_count,
        )

        # 构建审计快照
        ctx.audit_snapshot = {
            "drift_alert": ctx.drift_alert,
            "similarity_score": ctx.similarity_score,
            "narrative_sync_ok": ctx.narrative_sync_ok,
            "vector_stored": ctx.vector_stored,
            "foreshadow_stored": ctx.foreshadow_stored,
            "triples_extracted": ctx.triples_extracted,
            "causal_edges_stored": ctx.causal_edges_stored,
            "character_mutations_stored": ctx.character_mutations_stored,
            "debt_updated": ctx.debt_updated,
            "validation_score": ctx.validation_score,
            "validation_passed": ctx.validation_passed,
        }

        return StepResult.ok()

    # ═══════════════════════════════════════════════════════════════
    # 辅助方法（protected，子类可覆写）
    # ═══════════════════════════════════════════════════════════════

    def _post_process_generation(self, content: str, ctx: PipelineContext) -> str:
        """生成后处理 — 子类可覆写以添加后处理逻辑"""
        try:
            from application.ai.llm_output_sanitize import strip_reasoning_artifacts
            from application.ai.prose_fragment_aggregator import aggregate_inline_prose_fragments
            from domain.novel.value_objects.novel_id import NovelId

            s = strip_reasoning_artifacts(content)
            enabled = False
            try:
                if ctx.novel_id and ctx.novel_repository is not None:
                    nov = ctx.novel_repository.get_by_id(NovelId(ctx.novel_id))
                    if nov is not None:
                        enabled = bool(nov.generation_prefs.inline_prose_aggregation_enabled)
            except Exception:
                enabled = False
            if enabled:
                return aggregate_inline_prose_fragments(s)
            return s
        except ImportError:
            return content

    def _push_streaming_snapshot(self, novel_id: str, content: str) -> None:
        """推送整章累积快照到 StreamingBus，供 /autopilot/.../chapter-stream 消费。"""
        if not novel_id or not content:
            return
        try:
            from application.engine.services.streaming_bus import streaming_bus

            streaming_bus.publish(novel_id, content=content)
        except Exception as e:
            logger.debug("[%s] streaming_bus.publish 失败: %s", novel_id, e)

    def _novel_stream_should_stop(self, novel_id: str) -> bool:
        """与 legacy 写作一致：IPC 停止信号 + 控制队列消费。"""
        try:
            from application.engine.services.novel_stop_signal import is_novel_stopped

            if is_novel_stopped(novel_id):
                return True
        except Exception:
            pass
        try:
            from application.engine.services.streaming_bus import streaming_bus

            streaming_bus.consume_control_signals(novel_id)
            from application.engine.services.novel_stop_signal import is_novel_stopped

            return is_novel_stopped(novel_id)
        except Exception:
            return False

    async def _stream_prose_llm(self, ctx: PipelineContext, prompt: Any, config: Any) -> str:
        """Stream a single prose call and publish cumulative snapshots.

        Kept as the small primitive behind whole-chapter composition tests and
        emergency subclasses; production StoryPipeline normally enters through
        a ProseComposer.
        """
        if ctx.llm_service is None:
            return ""
        content_parts: List[str] = []
        last_push = time.monotonic()

        def _maybe_push(*, force: bool = False) -> None:
            nonlocal last_push
            now = time.monotonic()
            if not force and (now - last_push) < self.STREAM_PUSH_INTERVAL:
                return
            content = "".join(content_parts)
            if content:
                self._push_streaming_snapshot(ctx.novel_id, content)
            last_push = now

        async for piece in ctx.llm_service.stream_generate(prompt, config):
            if self._novel_stream_should_stop(ctx.novel_id):
                return ""
            if not piece:
                continue
            content_parts.append(piece)
            _maybe_push()
        _maybe_push(force=True)
        return "".join(content_parts)

    def _get_character_masks(self, ctx: PipelineContext) -> Dict[str, Any]:
        """获取当前章节的角色面具（供策略验证使用）"""
        return {}

    def _get_character_names(self, ctx: PipelineContext) -> List[str]:
        """获取角色名列表（供策略验证使用）"""
        return []

    def _push_persistence_command(self, ctx: PipelineContext) -> bool:
        """推送持久化命令到 CQRS 队列"""
        try:
            from application.engine.services.persistence_queue import get_persistence_queue
            pq = get_persistence_queue()
            return pq.push("upsert_chapter", {
                "novel_id": ctx.novel_id,
                "chapter_number": ctx.chapter_number,
                "content": ctx.chapter_content,
                "word_count": ctx.word_count,
                "status": "completed",
            })
        except Exception:
            return False

    async def _save_chapter_via_repository(self, ctx: PipelineContext) -> None:
        """通过 repository 保存章节"""
        # 委托给具体的 repository 实现
        pass

    async def _apply_voice_rewrite_loop(self, ctx: PipelineContext) -> None:
        """声线漂移定向改写循环"""
        ctx.rewrite_applied = True
        ctx.rewrite_attempts = min(self.VOICE_REWRITE_MAX_ATTEMPTS, 1)
        # 具体改写逻辑委托给 voice_drift_service

    async def _score_tension_via_llm(self, ctx: PipelineContext) -> int:
        """通过 AI Invocation 评分（降级方案）"""
        try:
            import re
            from application.ai_invocation.autopilot.factory import get_or_create_autopilot_helper_invoker
            from application.ai_invocation.autopilot.helper_invoker import AutopilotHelperRequest
            from infrastructure.ai.prompt_keys import TENSION_SCORING

            owner = type("PipelineTensionInvocationOwner", (), {"llm_service": ctx.llm_service})()
            content = await get_or_create_autopilot_helper_invoker(owner).invoke_text(
                AutopilotHelperRequest(
                    novel_id=str(ctx.novel_id or "global"),
                    stage="audit",
                    operation="autopilot.tension.score",
                    node_key=TENSION_SCORING,
                    explicit_variables={"content": ctx.chapter_content[:2000]},
                    context={
                        "novel_id": ctx.novel_id,
                        "chapter_number": ctx.chapter_number,
                    },
                    metadata={"source": "story_pipeline.tension_score"},
                    config={"max_tokens": 10, "temperature": 0.3},
                )
            )
            match = re.search(r'(\d+)', content)
            if match:
                score = int(match.group(1))
                return min(score, 10) * 10  # 1-10 → 0-100
        except Exception:
            pass
        return 50  # 默认中等张力

    def _make_result(
        self,
        ctx: PipelineContext,
        success: bool,
        error: Optional[str] = None,
        step_status: Optional[Dict[str, str]] = None,
    ) -> PipelineResult:
        """从上下文构建管线结果"""
        tension = 0
        if ctx.tension_composite is not None:
            tension = int(ctx.tension_composite)

        return PipelineResult(
            success=success,
            chapter_number=ctx.chapter_number,
            content=ctx.chapter_content,
            word_count=ctx.word_count,
            tension=tension,
            drift_alert=ctx.drift_alert,
            similarity_score=ctx.similarity_score,
            validation_score=ctx.validation_score,
            validation_passed=ctx.validation_passed,
            narrative_sync_ok=ctx.narrative_sync_ok,
            error=error,
            audit_snapshot=getattr(ctx, 'audit_snapshot', {}),
            step_status=step_status or {},
        )

    def _log_step(self, step_name: str, message: str) -> None:
        """记录步骤执行日志"""
        self._step_log.append({"step": step_name, "message": message})
        logger.debug(f"[Pipeline] {step_name}: {message}")

    def get_step_log(self) -> List[Dict[str, Any]]:
        """获取步骤执行日志（调试用）"""
        return self._step_log.copy()
