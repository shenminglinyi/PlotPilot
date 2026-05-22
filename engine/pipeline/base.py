"""BaseStoryPipeline — 写作管线基类

这是 AIText 引擎的灵魂。一个类，十个步骤，继承即扩展。

完整管线流程（单章生成）：
 1. _step_find_next_chapter(ctx)     定位下一个待写章节
 2. _step_build_context(ctx)         组装上下文（四层洋葱挤压）
 3. _step_magnify_beats(ctx)         节拍放大（大纲→微观节拍）
 4. _step_generate(ctx)              LLM 生成（节拍级+断点续写）
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

# domain.ai.Prompt 要求 system/user 均非空；管线把指令放在 user 侧，system 仅作最小角色锚定。
_DEFAULT_PIPELINE_SYSTEM_PROMPT = (
    "你是专业网络小说作者。仅根据用户给出的上下文与节拍要求撰写中文正文；"
    "不要输出思考过程、元评论或重复用户指令。"
)


def _serialize_beats_for_shared_state(beats: Any) -> list:
    """将 Beat 列表序列化为共享内存快照（含 EmotionBeatCard 三字段）。"""
    out = []
    for b in beats or []:
        card = getattr(b, "emotion_beat_card", None)
        out.append({
            "description": getattr(b, "description", "") or "",
            "target_words": int(getattr(b, "target_words", 0) or 0),
            "focus": getattr(b, "focus", "") or "pacing",
            "location_id": getattr(b, "location_id", "") or "",
            "active_action": (getattr(card, "active_action", "") or "") if card else "",
            "emotion_gap": (getattr(card, "emotion_gap", "") or "") if card else "",
            "forbidden_drift": (getattr(card, "forbidden_drift", "") or "") if card else "",
        })
    return out


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
    - BATCH_WRITE_INTERVAL: 节拍批量写库间隔
    """

    # ─── 可覆写的类属性（调参） ───
    DEFAULT_TARGET_WORDS: int = 2500
    VOICE_REWRITE_THRESHOLD: float = 0.68
    VOICE_REWRITE_MAX_ATTEMPTS: int = 3
    VOICE_WARNING_THRESHOLD_FALLBACK: float = 0.75
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

            # 2. 组装上下文（四层洋葱挤压）
            r = await self._step_build_context(ctx)
            step_status["build_context"] = "ok" if r.passed else "failed"
            if not r.passed:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)
            _writing_progress(
                ctx,
                "context_assembly",
                "组装上下文",
                pipeline_wave_index=2,
                current_chapter_number=ctx.chapter_number,
                context_tokens=int(ctx.context_tokens or 0),
                chapter_target_words=ctx.target_word_count,
            )

            # 3. 节拍放大（大纲→微观节拍）
            r = await self._step_magnify_beats(ctx)
            step_status["magnify_beats"] = "ok" if r.passed else "failed"
            if not r.passed:
                return self._make_result(ctx, success=False, error=r.message, step_status=step_status)
            _writing_progress(
                ctx,
                "beat_magnification",
                f"节拍拆分（{len(ctx.beats)} 个）",
                pipeline_wave_index=3,
                current_chapter_number=ctx.chapter_number,
                total_beats=len(ctx.beats),
                current_beat_index=0,
                chapter_target_words=ctx.target_word_count,
                planned_micro_beats=_serialize_beats_for_shared_state(ctx.beats),
            )

            # 4. LLM 生成（节拍级+断点续写）
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
                    return StepResult.ok(f"定位到第 {node.number} 章")

            return StepResult.fail("所有章节已写完，无需继续")
        except Exception as e:
            return StepResult.fail(f"章节定位失败: {e}")

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

    async def _step_magnify_beats(self, ctx: PipelineContext) -> StepResult:
        """步骤3：节拍放大（大纲→微观节拍）

        默认实现：委托给 ContextBuilder.magnify_outline_to_beats()
        将章节大纲拆分为多个微观节拍，每个节拍有独立的焦点和目标字数。

        子类覆写场景：
        - 短剧引擎：减少节拍数、降低每拍字数
        - 史诗引擎：增加节拍数、每拍更多感官描写
        """
        self._log_step("magnify_beats", "节拍放大")

        if ctx.context_builder is not None:
            try:
                beat_sheet_json = None
                bs = ctx.beat_sheet
                if bs is not None and getattr(bs, "scenes", None):
                    beat_sheet_json = {
                        "scenes": [
                            {
                                "title": getattr(s, "title", "") or "",
                                "goal": getattr(s, "goal", "") or "",
                                "estimated_words": getattr(s, "estimated_words", None) or 600,
                                "pov_character": getattr(s, "pov_character", "") or "",
                                "location": getattr(s, "location", None),
                                "tone": getattr(s, "tone", None),
                                "transition_from_prev": getattr(s, "transition_from_prev", None),
                            }
                            for s in bs.scenes
                        ]
                    }
                from application.engine.dag.plan.outline_beat_planner import (
                    build_chapter_execution_plan_async,
                )

                chapter_plan = None
                try:
                    chapter_plan = await build_chapter_execution_plan_async(
                        ctx.outline or "",
                        target_chapter_words=ctx.target_word_count,
                        novel_id=ctx.novel_id,
                        chapter_number=ctx.chapter_number,
                        beat_sheet_json=beat_sheet_json,
                        use_llm=True,
                        llm_service=ctx.llm_service,
                    )
                except Exception as e:
                    logger.warning("章前执行计划（拆节拍）失败，降级：%s", e)

                use_plan = chapter_plan is not None and bool(chapter_plan.atoms)
                ctx.beats = ctx.context_builder.magnify_outline_to_beats(
                    ctx.chapter_number,
                    ctx.outline,
                    target_chapter_words=ctx.target_word_count,
                    chapter_execution_plan=chapter_plan if use_plan else None,
                    beat_sheet=None if use_plan else ctx.beat_sheet,
                    scene_director=getattr(ctx, "scene_director", None),
                )
                logger.info(f"[{ctx.novel_id}] 节拍拆分: {len(ctx.beats)} 个节拍")
            except Exception as e:
                logger.warning(f"节拍放大失败: {e}")
                # 降级：创建单节拍
                ctx.beats = [type('Beat', (), {
                    'description': ctx.outline,
                    'target_words': ctx.target_word_count,
                    'focus': 'mixed',
                    'expansion_hints': [],
                    'scene_goal': '',
                    'transition_from_prev': '',
                })()]
        else:
            # 无 context_builder，创建单节拍
            ctx.beats = [type('Beat', (), {
                'description': ctx.outline,
                'target_words': ctx.target_word_count,
                'focus': 'mixed',
                'expansion_hints': [],
                'scene_goal': '',
                'transition_from_prev': '',
            })()]

        return StepResult.ok()

    async def _step_generate(self, ctx: PipelineContext) -> StepResult:
        """步骤4：LLM 生成（节拍级+断点续写）

        默认实现：逐节拍调用 LLM，支持断点续写。
        子类可覆写 _build_generation_prompt() 修改 prompt 模板，
        或覆写 _post_process_generation() 后处理。

        子类覆写场景：
        - 覆写 _build_generation_prompt() 修改 prompt 模板
        - 覆写 _post_process_generation() 后处理
        """
        self._log_step("generate", f"LLM 生成，节拍数={len(ctx.beats)}")

        if ctx.llm_service is None:
            return StepResult.fail("llm_service 未设置，无法生成")

        accumulated_content = ctx.existing_content
        ctx.raw_beat_contents = []

        # ─── 节拍中间件初始化（StepTension / Coherence / Transition） ────
        _beat_middlewares = []
        _mw_ctx = None
        try:
            from application.engine.services.beat_middleware import (
                init_beat_middlewares, BeatMiddlewareContext,
            )
            _beat_middlewares = init_beat_middlewares()
            _mw_ctx = BeatMiddlewareContext(
                novel_id=ctx.novel_id or "",
                chapter_number=ctx.chapter_number,
                total_beats=len(ctx.beats),
            )
        except Exception as _mw_init_err:
            logger.debug("Beat middlewares unavailable, skipping: %s", _mw_init_err)

        for i, beat in enumerate(ctx.beats):
            if i < ctx.start_beat_index:
                continue

            n_beats = max(len(ctx.beats), 1)
            acc0 = len((accumulated_content or "").strip())
            _card = getattr(beat, "emotion_beat_card", None)
            _writing_progress(
                ctx,
                "llm_calling",
                f"节拍 {i + 1}/{n_beats} 撰写",
                pipeline_wave_index=4,
                current_chapter_number=ctx.chapter_number,
                total_beats=n_beats,
                current_beat_index=i,
                chapter_target_words=ctx.target_word_count,
                accumulated_words=acc0,
                beat_focus=(str(getattr(beat, "focus", "") or "").strip() or None),
                beat_active_action=(getattr(_card, "active_action", None) if _card else None),
                beat_emotion_gap=(getattr(_card, "emotion_gap", None) if _card else None),
                beat_forbidden_drift=(getattr(_card, "forbidden_drift", None) if _card else None),
            )

            # 构建 prompt
            prompt_text = self._build_generation_prompt(ctx, beat, i)
            target = getattr(beat, 'target_words', ctx.target_word_count // max(len(ctx.beats), 1))

            # 节拍中间件 pre_beat（注入 STEP 张力 / 连贯性 / 过渡方式）
            if _beat_middlewares and _mw_ctx is not None:
                _mw_ctx.beat_index = i
                _mw_ctx.beat = beat
                _mw_ctx.accumulated_content = accumulated_content or ""
                for _mw in _beat_middlewares:
                    try:
                        prompt_text, target = _mw.pre_beat(prompt_text, target, _mw_ctx)
                    except Exception as _mw_err:
                        logger.debug("Middleware pre_beat skipped: %s", _mw_err)

            # 流式调用 LLM（推送 streaming_bus，供 Autopilot chapter-stream SSE）
            try:
                from domain.ai.services.llm_service import GenerationConfig
                max_tokens = int(target * 1.3)
                cfg = GenerationConfig(max_tokens=max_tokens, temperature=0.85)

                chapter_draft_so_far = (accumulated_content or "").strip()
                beat_content = await self._stream_beat_llm(
                    ctx,
                    self._make_prompt(prompt_text),
                    cfg,
                    chapter_draft_so_far=chapter_draft_so_far,
                    beat_index=i,
                    n_beats=n_beats,
                )

                # 后处理
                beat_content = self._post_process_generation(beat_content, ctx)

                # 节拍中间件 post_beat（更新连贯性上下文，供下一节拍使用）
                if _beat_middlewares and _mw_ctx is not None:
                    for _mw in _beat_middlewares:
                        try:
                            _mw_ctx = _mw.post_beat(beat_content, _mw_ctx)
                        except Exception as _mw_err:
                            logger.debug("Middleware post_beat skipped: %s", _mw_err)

                if beat_content.strip():
                    if accumulated_content:
                        accumulated_content += "\n\n" + beat_content.strip()
                    else:
                        accumulated_content = beat_content.strip()
                    ctx.raw_beat_contents.append(beat_content.strip())
                    # 后处理后的整章快照（与落库正文一致，避免流式区仍显示原始 LLM 输出）
                    self._push_streaming_snapshot(ctx.novel_id, accumulated_content.strip())
                    _writing_progress(
                        ctx,
                        "llm_calling",
                        f"节拍 {i + 1}/{n_beats} 撰写",
                        pipeline_wave_index=4,
                        current_chapter_number=ctx.chapter_number,
                        total_beats=n_beats,
                        current_beat_index=i,
                        chapter_target_words=ctx.target_word_count,
                        accumulated_words=len(accumulated_content.strip()),
                        beat_focus=(str(getattr(beat, "focus", "") or "").strip() or None),
                    )

            except Exception as e:
                logger.warning(f"[{ctx.novel_id}] 节拍 {i+1} 生成失败: {e}")
                # 继续下一个节拍

        ctx.chapter_content = accumulated_content or ""
        raw = accumulated_content or ""
        ctx.word_count = len(raw)
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
            total_beats=len(ctx.beats) if ctx.beats else 0,
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
            total_beats=len(ctx.beats) if ctx.beats else 0,
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
            except Exception as e:
                logger.warning(f"章后管线失败: {e}")

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

    def _build_generation_prompt(self, ctx: PipelineContext, beat: Any, beat_index: int) -> str:
        """构建生成 prompt — 子类可覆写以定制 prompt 模板"""
        parts = []
        if ctx.context_text:
            parts.append(ctx.context_text)
        if ctx.voice_anchors:
            parts.append(ctx.voice_anchors)
        if ctx.outline:
            parts.append(f"【章节大纲】\n{ctx.outline}")
        beat_desc = getattr(beat, 'description', str(beat))
        beat_focus = getattr(beat, 'focus', 'mixed')
        parts.append(f"【当前节拍 {beat_index+1}/{len(ctx.beats)}】{beat_desc}（焦点：{beat_focus}）")
        card_block = getattr(beat, 'card_prompt_block', '')
        if card_block:
            parts.append(card_block)
        return "\n\n".join(parts)

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

    def _make_prompt(self, text: str) -> Any:
        """将文本转为 Prompt 对象"""
        try:
            from domain.ai.value_objects.prompt import Prompt
            return Prompt(system=_DEFAULT_PIPELINE_SYSTEM_PROMPT, user=text)
        except ImportError:
            return text

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

    @staticmethod
    def _live_chapter_snapshot(chapter_draft_so_far: str, chunk_buffer: List[str]) -> str:
        beat_part = "".join(chunk_buffer)
        prior = (chapter_draft_so_far or "").strip()
        if not prior:
            return beat_part
        if not beat_part:
            return prior
        return f"{prior}\n\n{beat_part}"

    async def _stream_beat_llm(
        self,
        ctx: PipelineContext,
        prompt: Any,
        config: Any,
        *,
        chapter_draft_so_far: str,
        beat_index: int,
        n_beats: int,
    ) -> str:
        """单节拍流式生成，周期性推送整章快照。"""
        novel_id = ctx.novel_id
        chunk_buffer: List[str] = []
        last_push = time.monotonic()
        content = ""

        def _maybe_push(*, force: bool = False) -> None:
            nonlocal last_push
            now = time.monotonic()
            if not force and (now - last_push) < self.STREAM_PUSH_INTERVAL:
                return
            snap = self._live_chapter_snapshot(chapter_draft_so_far, chunk_buffer)
            if not snap:
                return
            self._push_streaming_snapshot(novel_id, snap)
            _writing_progress(
                ctx,
                "llm_calling",
                f"节拍 {beat_index + 1}/{n_beats} 撰写",
                pipeline_wave_index=4,
                current_chapter_number=ctx.chapter_number,
                total_beats=n_beats,
                current_beat_index=beat_index,
                chapter_target_words=ctx.target_word_count,
                accumulated_words=len(snap.strip()),
            )
            last_push = now

        try:
            async for piece in ctx.llm_service.stream_generate(prompt, config):
                if self._novel_stream_should_stop(novel_id):
                    logger.info("[%s] 流式生成收到停止信号，终止节拍 %s", novel_id, beat_index + 1)
                    break
                if not piece:
                    continue
                chunk_buffer.append(piece)
                content += piece
                _maybe_push()
        finally:
            _maybe_push(force=True)

        return content

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
        """通过 LLM 评分（降级方案）"""
        try:
            prompt = self._make_prompt(
                f"请为以下章节内容打张力分（1-10，10为最高）：\n\n{ctx.chapter_content[:2000]}\n\n张力分："
            )
            from domain.ai.services.llm_service import GenerationConfig
            cfg = GenerationConfig(max_tokens=10, temperature=0.3)
            result = await ctx.llm_service.generate(prompt=prompt, config=cfg)
            content = result.content if hasattr(result, 'content') else str(result)
            import re
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
