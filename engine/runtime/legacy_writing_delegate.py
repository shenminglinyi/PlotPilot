"""Legacy 写作委托 — Phase 6 从 AutopilotDaemon 迁入 engine/runtime

节拍级幂等落库 + 章节完整性保证。新内核写作见 writing_delegate.run_story_pipeline_writing。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from domain.ai.services.llm_service import GenerationConfig
from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.novel.entities.chapter import ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import StoryNode

logger = logging.getLogger(__name__)


async def run_legacy_writing(host: Any, novel: Novel) -> None:
    """Legacy 写作（节拍级生成 + 断点续写）— host 提供基础设施 helper"""
    if not host._is_still_running(novel):
        return

    # 0. 叙事结构被清空（无任何卷）：DB 阶段往往仍为 writing，否则会先显示「写作」
    #    再白等一轮幕级规划才发现无卷。此处立即回到宏观规划并刷新共享内存。
    novel_id_v = novel.novel_id.value
    try:
        all_nodes_early = await host.story_node_repo.get_by_novel(novel_id_v)
        volume_nodes_early = [
            n for n in all_nodes_early if getattr(n.node_type, "value", n.node_type) == "volume"
        ]
        if not volume_nodes_early:
            logger.warning(
                "[%s] 无卷节点（结构可能被清空），写作阶段立即回到宏观规划",
                novel_id_v,
            )
            novel.current_stage = NovelStage.MACRO_PLANNING
            novel.current_act = 0
            novel.current_chapter_in_act = 0
            novel.current_beat_index = 0
            host._update_shared_state(
                novel_id_v,
                current_stage="macro_planning",
                writing_substep="macro_planning",
                writing_substep_label="宏观规划",
            )
            host._flush_novel(novel)
            return
    except Exception as e:
        logger.debug("[%s] 写作前结构探测失败（忽略）: %s", novel_id_v, e)

    # 1. 目标控制：达到目标章节数则自动停止
    target_chapters = novel.target_chapters or 50
    max_chapters = novel.max_auto_chapters or 9999
    current_chapters = novel.current_auto_chapters or 0

    if current_chapters >= target_chapters:
        logger.info(f"[{novel.novel_id}] 已达到目标章节数 {target_chapters} 章，全托管完成")
        novel.autopilot_status = AutopilotStatus.STOPPED
        novel.current_stage = NovelStage.COMPLETED
        return

    if current_chapters >= max_chapters:
        logger.info(f"[{novel.novel_id}] 已达保护上限 {max_chapters} 章，自动暂停")
        novel.autopilot_status = AutopilotStatus.STOPPED
        novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
        return


    # 2. 余韵章判断（高潮后插入余韵章——不再是"日常过渡"，而是"高潮余波"）
    # ★ Phase 1: 统一使用 0-100 刻度。阈值 80 对应旧 8/10
    # 兼容旧数据：如果值 <= 10 视为旧刻度，自动 ×10
    raw_tension = novel.last_chapter_tension or 0
    tension_100 = raw_tension * 10 if raw_tension <= 10 else raw_tension
    needs_buffer = tension_100 >= 80
    if needs_buffer:
        logger.info(f"[{novel.novel_id}] 上章张力≥80（raw={raw_tension}），触发余韵章")

    # 3. 找下一个未写章节
    next_chapter_node = await host._find_next_unwritten_chapter_async(novel)
    if not next_chapter_node:
        # 🔥 修复：找不到下一章时，检查当前幕是否全部写完
        if await host._current_act_fully_written(novel):
            # 当前幕已完成，进入下一幕规划
            novel.current_act += 1
            novel.current_chapter_in_act = 0
            novel.current_stage = NovelStage.ACT_PLANNING
            logger.info(f"[{novel.novel_id}] 当前幕已完成，进入第 {novel.current_act + 1} 幕规划")
        else:
            # 🔥 修复：当前幕还有章节但找不到未写章节，说明章节节点可能未创建
            # 进入幕级规划创建章节节点，而不是跳到审计
            novel.current_stage = NovelStage.ACT_PLANNING
            logger.info(f"[{novel.novel_id}] 找不到下一章节点，进入幕级规划创建章节")
        return

    chapter_num = next_chapter_node.number
    host._sync_novel_current_act_from_chapter_story_node(novel, next_chapter_node)
    host._cache_stats_to_shared_memory(novel)
    outline = next_chapter_node.outline or next_chapter_node.description or next_chapter_node.title

    # 合并分章叙事节拍
    if host.knowledge_service:
        try:
            knowledge = host.knowledge_service.get_knowledge(novel.novel_id.value)
            chapter_entry = next(
                (ch for ch in knowledge.chapters if str(ch.chapter_id) == str(chapter_num)),
                None
            )
            if chapter_entry and getattr(chapter_entry, "beat_sections", None):
                beats_text = "\n".join(str(b) for b in chapter_entry.beat_sections if b)
                if beats_text.strip():
                    outline = f"【分章叙事节拍】\n{beats_text}\n\n【章节大纲】\n{outline}"
                    logger.info(f"[{novel.novel_id}] 已合并第{chapter_num}章分章叙事节拍（{len(chapter_entry.beat_sections)}条）")
        except Exception as _e:
            logger.warning(f"[{novel.novel_id}] 读取分章叙事失败，使用原始大纲：{_e}")

    if needs_buffer:
        # ★ Phase 1: 缓冲章 → 余韵模式
        # 不再"突然日常化"，而是让角色消化冲击、新线索浮现、势力格局变动
        outline = (
            f"【余韵章：高潮余波】{outline}。"
            f"本章节奏适度放缓但不中断叙事势能——"
            f"角色消化刚刚发生的重大冲击（震惊/损失/获得），"
            f"周围势力对主角态度发生明显变化，"
            f"新的暗线/线索/威胁在余波中悄然浮现。"
            f"确保读者在喘息中依然保持期待，而不是「聊天喝茶」式断裂。"
        )

    target_word_count = int(getattr(novel, "target_words_per_chapter", None) or 2500)
    logger.info(f"[{novel.novel_id}] 开始写第 {chapter_num} 章：{outline[:60]}...")
    logger.info(f"[{novel.novel_id}]    进度: {current_chapters}/{target_chapters} 章（目标 {target_word_count} 字/章）")

    # ★ 子步骤状态：找到下一章
    host._update_shared_state(
        novel.novel_id.value,
        writing_substep="chapter_found",
        writing_substep_label="章节定位",
        current_chapter_number=chapter_num,
        planned_micro_beats=[],
        outline_plan_mode="",
        total_beats=0,
    )

    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止，跳过本章（上下文组装前）")
        return

    # 4. 获取规划阶段的 BeatSheet（如果有）
    beat_sheet = await host._get_beat_sheet_for_chapter(novel.novel_id.value, chapter_num)
    if beat_sheet:
        logger.info(f"[{novel.novel_id}] 使用规划阶段的 BeatSheet：{len(beat_sheet.scenes)} 个场景")

    # ★ 子步骤状态：开始组装上下文
    host._update_shared_state(
        novel.novel_id.value,
        writing_substep="context_assembly",
        writing_substep_label="组装上下文",
        current_chapter_number=chapter_num,
    )

    # 5. 组装上下文
    bundle = None
    context = ""
    if host.chapter_workflow:
        try:
            bundle = host.chapter_workflow.prepare_chapter_generation(
                novel.novel_id.value, chapter_num, outline, scene_director=None
            )
            context = bundle["context"]
            logger.info(
                f"[{novel.novel_id}]    上下文（workflow）: {len(context)} 字符, "
                f"约 {bundle['context_tokens']} tokens"
            )
        except Exception as e:
            if str(e).startswith("evolution_gate_blocked:"):
                logger.warning(
                    "[%s] EvolutionGate blocking，第 %s 章暂停托管写作：%s",
                    novel.novel_id.value,
                    chapter_num,
                    str(e).replace("evolution_gate_blocked:", ""),
                )
                novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
                novel.autopilot_status = AutopilotStatus.STOPPED
                host._update_shared_state(
                    novel.novel_id.value,
                    current_stage="paused_for_review",
                    writing_substep="evolution_gate_blocked",
                    writing_substep_label="故事演进 Gate 阻断",
                    evolution_gate_message=str(e).replace("evolution_gate_blocked:", ""),
                )
                host._flush_novel(novel)
                return
            logger.warning(f"prepare_chapter_generation 失败，尝试降级：{e}")
            try:
                bundle = host.chapter_workflow.build_fallback_chapter_bundle(
                    novel.novel_id.value, chapter_num, outline, scene_director=None, max_tokens=20000,
                )
                context = bundle["context"]
            except Exception as e2:
                logger.warning(f"降级失败：{e2}")
                bundle = None
    if bundle is None and host.context_builder:
        try:
            context = host.context_builder.build_context(
                novel_id=novel.novel_id.value, chapter_number=chapter_num, outline=outline, max_tokens=20000,
            )
        except Exception as e:
            logger.warning(f"ContextBuilder.build_context 失败：{e}")

    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止（上下文组装后）")
        return

    voice_anchors = ""
    if bundle is not None:
        voice_anchors = bundle.get("voice_anchors") or ""
    elif host.context_builder:
        try:
            voice_anchors = host.context_builder.build_voice_anchor_system_section(novel.novel_id.value)
        except Exception:
            voice_anchors = ""

    # 6. 节拍放大：先走章前执行计划（与 DAG planning_outline_partition / CPMS 同源），再投影为 Beat
    beats: List[Any] = []
    planned_mb: List[Dict[str, Any]] = []
    plan_mode = ""
    if host.context_builder:
        beat_sheet_json = host._beat_sheet_to_plan_json(beat_sheet)
        chapter_plan = None
        try:
            from application.engine.dag.plan.outline_beat_planner import (
                build_chapter_execution_plan_async,
            )

            logger.info(
                "[%s] 📑 章前规划开始（outline_planning / CPMS outline-beat-partition）第 %s 章",
                novel.novel_id.value,
                chapter_num,
            )
            host._update_shared_state(
                novel.novel_id.value,
                writing_substep="outline_planning",
                writing_substep_label="章前规划 · 划分节拍",
                current_chapter_number=chapter_num,
                context_tokens=bundle.get("context_tokens", 0) if bundle else 0,
                planned_micro_beats=[],
                outline_plan_mode="",
                total_beats=0,
            )

            async def _emit_outline_planning_delta(_piece: str) -> None:
                if not _piece:
                    return
                host._update_shared_state(
                    novel.novel_id.value,
                    writing_substep="outline_planning",
                    writing_substep_label="章前规划 · 流式划分节拍…",
                )

            chapter_plan = await build_chapter_execution_plan_async(
                outline,
                target_chapter_words=target_word_count,
                novel_id=novel.novel_id.value,
                chapter_number=chapter_num,
                beat_sheet_json=beat_sheet_json,
                use_llm=True,
                emit_llm_delta=_emit_outline_planning_delta,
                llm_service=host.llm_service,
            )
        except Exception as e:
            logger.warning(
                "[%s] 章前执行计划（拆节拍）失败，降级为同步 ChapterExecutionPlan：%s",
                novel.novel_id.value,
                e,
            )
            try:
                from application.engine.dag.plan.outline_beat_planner import (
                    build_chapter_execution_plan_sync,
                )
                chapter_plan = build_chapter_execution_plan_sync(
                    outline,
                    target_chapter_words=target_word_count,
                    novel_id=novel.novel_id.value,
                    chapter_number=chapter_num,
                    beat_sheet_json=beat_sheet_json,
                    decomposition_label="legacy_writing_sync_fallback",
                )
            except Exception as sync_err:
                logger.error("[%s] 同步 ChapterExecutionPlan 构建失败: %s", novel.novel_id.value, sync_err)
                chapter_plan = None

        beats = host.context_builder.magnify_outline_to_beats(
            chapter_num,
            outline,
            target_chapter_words=target_word_count,
            chapter_execution_plan=chapter_plan,
            beat_sheet=None,
        )

        plan_mode = ""
        if chapter_plan is not None and isinstance(getattr(chapter_plan, "provenance", None), dict):
            plan_mode = str(chapter_plan.provenance.get("mode") or "")
        planned_mb = host._beats_to_planned_micro_beats(beats)
        logger.info(
            "[%s] ✓ 章前规划完成 mode=%s → %d 个指挥器节拍（第 %s 章）",
            novel.novel_id.value,
            plan_mode or "unknown",
            len(beats),
            chapter_num,
        )

    # ★ 子步骤状态：节拍拆分完成
    host._update_shared_state(
        novel.novel_id.value,
        writing_substep="beat_magnification",
        writing_substep_label=f"节拍拆分（{len(beats)}个）",
        total_beats=len(beats),
        planned_micro_beats=planned_mb,
        outline_plan_mode=plan_mode,
        context_tokens=bundle.get('context_tokens', 0) if bundle else 0,
    )

    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止（节拍拆分后）")
        return

    # 6. 节拍级生成 + 断点续写 + 完整性保证
    start_beat = novel.current_beat_index or 0
    entry_start_beat = start_beat  # 记录本轮入口节拍索引，用于死锁检测
    beats_completed = getattr(novel, 'beats_completed', False)
    chapter_content = await host._get_existing_chapter_content(novel, chapter_num) or ""
    use_wf = host.chapter_workflow is not None and bundle is not None

    # 断点续写：使用已有的章节内容作为上下文
    existing_content = chapter_content.strip()

    # === 关键检查：章节是否已完成 ===
    # 🔥 修复：审计完成后回到 WRITING，这一章已经审计过了（completed+已审计），
    # 不应再进入 AUDITING 重复审计。应跳过这一章，下一轮找新的未写章节。
    existing_chapter = host.chapter_repository.get_by_novel_and_number(
        NovelId(novel.novel_id.value), chapter_num
    )
    already_audited = (
        getattr(novel, 'last_audit_chapter_number', None) == chapter_num
    )
    if existing_chapter and existing_chapter.status == ChapterStatus.COMPLETED:
        if already_audited:
            # 审计完的 completed 章节，直接跳过（下一轮 _find_next_unwritten_chapter_async 会跳过 completed）
            logger.info(
                f"[{novel.novel_id}] 章节 {chapter_num} 已写完且已审计，等待下一轮找新章节"
            )
            return
        else:
            # 写完但未审计 → 正常进入审计
            logger.info(
                f"[{novel.novel_id}] 章节 {chapter_num} 已是 completed 状态但未审计，进入审计"
            )
            novel.current_stage = NovelStage.AUDITING
            host._flush_novel(novel)
            return

    # 检查已有内容是否达标（>= 70%）
    # 🔥 修复：如果这一章已经审计过（last_audit_chapter_number 匹配），
    # 说明是从审计回来后持久化队列延迟导致章节还是 draft，
    # 不应再次标记完成+审计，应确保 DB 状态正确后等下一轮找新章节
    if existing_content and len(existing_content) >= target_word_count * 0.7:
        if already_audited:
            logger.warning(
                f"[{novel.novel_id}] 章节 {chapter_num} 已审计过但 DB 仍为 draft "
                f"(持久化队列延迟)，强制补写 completed 后等下一轮"
            )
            # 🔥 关键修复：强制直接写 DB 确保章节状态为 completed
            # 这样下一轮 _find_next_unwritten_chapter_async 就不会再找到这一章
            if existing_chapter:
                # 🔥 核心修复：使用独立短连接写入 completed 状态
                host._save_chapter_ephemeral(
                    novel.novel_id.value, chapter_num,
                    status="completed",
                )
            else:
                await host._upsert_chapter_content(
                    novel, next_chapter_node, existing_content, status="completed"
                )
            # return 让下一轮主循环重新进入 _handle_writing
            # 此时 DB 中章节已是 completed，_find_next_unwritten_chapter_async 会跳过它
            return
        # ★ 禁止「字数够 70% 但节拍未跑完」提前结章——否则会断在章纲中段就去写下一章
        nb = len(beats)
        cidx = novel.current_beat_index or 0
        # 仅用索引判断；beats_completed 曾可能被错误置位，不能作为提前结章依据
        beats_all_done = nb == 0 or cidx >= nb
        if nb > 0 and not beats_all_done:
            logger.info(
                f"[{novel.novel_id}] 章节 {chapter_num} 已有 {len(existing_content)} 字 "
                f"(≥70%)，但节拍未完（current_beat_index={cidx}/{nb}），"
                f"不提前结章，继续节拍循环"
            )
        else:
            logger.info(
                f"[{novel.novel_id}] 章节 {chapter_num} 已有 {len(existing_content)} 字 "
                f"(达标 {int(len(existing_content) / target_word_count * 100)}%)，直接标记完成"
            )
            await host._upsert_chapter_content(
                novel, next_chapter_node, existing_content, status="completed"
            )
            novel.current_auto_chapters = (novel.current_auto_chapters or 0) + 1
            novel.current_chapter_in_act += 1
            novel.current_beat_index = 0
            novel.beats_completed = False
            novel.current_stage = NovelStage.AUDITING
            host._flush_novel(novel)
            return

    # 若上一轮已标「节拍全跑完」但未达到放行条件：禁止清回节拍 0 叠写
    if beats_completed:
        logger.info(
            f"[{novel.novel_id}] 节拍已全量跑过但未收章，保持断点索引，不回到第 1 拍重复生成"
        )
        novel.beats_completed = False
        if (novel.current_beat_index or 0) > len(beats):
            novel.current_beat_index = len(beats)
        start_beat = novel.current_beat_index or len(beats)

    # 关键检查：节拍索引超出范围——仅有正文时不要 reset 到 0（避免整章叠写）
    if start_beat >= len(beats) and len(beats) > 0:
        if existing_content.strip():
            logger.warning(
                f"[{novel.novel_id}] 节拍索引 {start_beat} >= {len(beats)} 且已有正文，"
                f"视为节拍已遍历完，进入收章复核（不重置为 0）"
            )
            novel.current_beat_index = len(beats)
            start_beat = len(beats)
        else:
            logger.warning(
                f"[{novel.novel_id}] 节拍索引 {start_beat} 超出范围 {len(beats)} 且无正文，"
                f"重置为 0"
            )
            start_beat = 0
            novel.current_beat_index = 0
            novel.beats_completed = False

    # 日志：start_beat 为 0-based；当 start_beat == len(beats) 时表示节拍已耗尽、仅收章复核，
    # 不得再打印「从第 len+1 拍继续」，否则会出现「从第 2/1 拍继续」类矛盾日志。
    if existing_content and len(beats) > 0:
        if 0 < start_beat < len(beats):
            logger.info(
                f"[{novel.novel_id}] 断点续写：已有 {len(existing_content)} 字，"
                f"从第 {start_beat + 1}/{len(beats)} 个节拍继续"
            )
        elif start_beat >= len(beats):
            logger.info(
                f"[{novel.novel_id}] 断点续写：已有 {len(existing_content)} 字，"
                f"节拍已全部处理（{len(beats)}/{len(beats)}），进入收章复核（本轮不再撰写新节拍）"
            )

    # 批量写入计数器
    write_counter = 0
    BATCH_WRITE_INTERVAL = 3  # 每 3 个节拍写入一次 DB

    # 累积的章节内容
    accumulated_content = existing_content

    # 章节指挥（三阶段收束：铺陈→收束→着陆）
    from application.engine.services.word_count_tracker import ChapterConductor
    conductor = ChapterConductor(
        total_budget=target_word_count,
        total_beats=len(beats) if beats else 0,
        converge_threshold=novel.generation_prefs.conductor_converge_threshold,
        land_threshold=novel.generation_prefs.conductor_land_threshold,
    )
    # 如果有已存在内容，先同步
    if existing_content:
        conductor.used = len(existing_content)

    # ★ Phase 0: 初始化节拍中间件链（低侵入式增强）
    from application.engine.services.beat_middleware import init_beat_middlewares, BeatMiddlewareContext
    beat_middlewares = init_beat_middlewares(conductor=conductor)
    mw_ctx = BeatMiddlewareContext(
        novel_id=novel.novel_id.value,
        chapter_number=chapter_num,
        total_beats=len(beats),
        accumulated_content=existing_content,
    )

    if beats:
        # 🧠 V3 CoT 桥接字典：key=beat_index(0-based)，value=BeatBridge
        # 每个节拍完成后异步计算下一节拍的桥接，在下一节拍 build_beat_prompt 时注入
        _beat_cot_bridges: dict = {}

        for i, beat in enumerate(beats):
            if i < start_beat:
                continue  # 跳过已生成的节拍

            # 获取指挥信号（铺陈/收束/着陆）——须在共享状态写入前取得，供遥测字段使用
            signal = conductor.get_signal(i)
            # 🔥 节拍开始前，立即更新共享状态（前端实时看到当前节拍）
            beat_focus = getattr(beat, 'focus', '') or ''
            beat_target_words = getattr(beat, 'target_words', 0) or 0
            host._update_shared_state(
                novel.novel_id.value,
                current_beat_index=i,
                writing_substep="llm_calling",
                writing_substep_label=f"节拍 {i+1}/{len(beats)} 撰写",
                total_beats=len(beats),
                beat_focus=beat_focus,
                beat_target_words=beat_target_words,
                accumulated_words=len(accumulated_content),
                chapter_target_words=target_word_count,
                context_tokens=bundle.get('context_tokens', 0) if bundle else 0,
                beat_hard_cap=0,
                beat_phase=signal.phase.value,
                beat_max_words_hint=int(signal.max_words_hint or 0),
                beat_remaining_budget=int(signal.remaining_budget),
                last_smart_truncate=None,
            )

            if not host._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 用户已停止，中断本章（节拍 {i + 1}/{len(beats)} 前）")
                # 保存已完成的内容和节拍索引
                if accumulated_content.strip():
                    # 流式被中断时，最后一个节拍可能在句子中间被截断。
                    # 截断到最近的句子边界，避免残篇以半句结尾落盘。
                    safe_content = accumulated_content.strip()
                    if not re.search(r'[。！？…）】》""\'』」]$', safe_content):
                        last_ender = max(
                            safe_content.rfind('。'),
                            safe_content.rfind('！'),
                            safe_content.rfind('？'),
                            safe_content.rfind('…'),
                        )
                        if last_ender > len(safe_content) * 0.4:
                            safe_content = safe_content[:last_ender + 1]
                            logger.info(
                                f"[{novel.novel_id}] 🔪 中断截断：{len(accumulated_content.strip())} "
                                f"→ {len(safe_content)} 字（截至句尾）"
                            )
                    await host._upsert_chapter_content(
                        novel, next_chapter_node, safe_content, status="draft"
                    )
                    novel.current_beat_index = i  # 记录当前节拍索引，下次从断点继续
                    host._flush_novel(novel)
                    logger.info(
                        f"[{novel.novel_id}] 已保存 {len(safe_content)} 字，"
                        f"下次从节拍 {i + 1} 继续"
                    )
                return

            adjusted_target = conductor.allocate_beat(beat.target_words, focus=beat.focus)  # ★ Phase 2: 传入 focus 用于免疫判断

            # 🧠 V3 CoT 桥接：从预计算字典取桥接对象（由上一节拍完成后异步计算）
            _cot_bridge = _beat_cot_bridges.get(i)
            beat_prompt = host.context_builder.build_beat_prompt(beat, i, len(beats), beat_bridge=_cot_bridge)

            # 🔗 V2：注入上一节拍的衔接诊断提示（如果有且无 CoT 桥接时）
            if not _cot_bridge and hasattr(novel, '_beat_continuity_hint') and novel._beat_continuity_hint:
                beat_prompt = f"{novel._beat_continuity_hint}\n\n{beat_prompt}"
                logger.debug(f"[{novel.novel_id}] 注入节拍衔接诊断到 beat {i+1}")

            # ★ Phase 0: 中间件 pre_beat 钩子（连贯性/过渡/能量免疫）
            mw_ctx.beat_index = i
            mw_ctx.beat = beat
            mw_ctx.original_adjusted_target = adjusted_target
            mw_ctx.phase = signal.phase.value
            mw_ctx.accumulated_content = accumulated_content
            for mw in beat_middlewares:
                try:
                    beat_prompt, adjusted_target = mw.pre_beat(beat_prompt, adjusted_target, mw_ctx)
                except Exception as e:
                    logger.debug(f"中间件 pre_beat 异常（不影响主流程）: {e}")

            # 注入指挥信号——核心：引导 LLM 自然收束
            # 1. 阶段指令（铺陈/收束/着陆）
            if signal.beat_instruction:
                beat_prompt = f"{signal.beat_instruction}\n\n{beat_prompt}"

            # 2. 最后节拍的章节收尾提示
            if signal.chapter_ending_hint:
                beat_prompt = f"{beat_prompt}\n\n{signal.chapter_ending_hint}"

            # 3. 兼容旧接口的紧急约束
            urgency_hint = conductor.get_urgency_hint()
            if urgency_hint and not signal.beat_instruction:
                beat_prompt = f"{urgency_hint}\n\n{beat_prompt}"

            if use_wf:
                prompt = host.chapter_workflow.build_chapter_prompt(
                    bundle["context"], outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    beat_prompt=beat_prompt,
                    beat_index=i, total_beats=len(beats),
                    beat_target_words=int(adjusted_target),  # 使用调整后的目标
                    voice_anchors=voice_anchors,
                    chapter_draft_so_far=accumulated_content,
                )
                max_tokens = int(adjusted_target * 1.3)  # 使用调整后的目标
                cfg = GenerationConfig(max_tokens=max_tokens, temperature=0.85)
                beat_content = await host._stream_llm_with_stop_watch(
                    prompt, cfg, novel=novel, chapter_draft_so_far=accumulated_content
                )
            else:
                beat_content = await host._stream_one_beat(
                    outline, context, beat_prompt, beat,
                    novel=novel, voice_anchors=voice_anchors,
                    chapter_draft_so_far=accumulated_content,
                )

            if beat_content.strip():
                # 不再做硬截断或截断后补写。超额由后续章节完成判定和节拍预算调度处理。

                # 报告实际字数给指挥
                actual_words = len(beat_content.strip())
                deviation = conductor.report_actual(actual_words)
                if deviation > 50:
                    logger.info(
                        f"[{novel.novel_id}] 节拍 {i + 1}/{len(beats)}: "
                        f"实际 {actual_words} 字，超额 {deviation} 字"
                    )

                # 累积内容
                if accumulated_content:
                    accumulated_content += "\n\n" + beat_content.strip()
                else:
                    accumulated_content = beat_content.strip()
                write_counter += 1

                # ★ Phase 0: 中间件 post_beat 钩子（上下文提取/情绪推断）
                mw_ctx.prev_beat_content = beat_content.strip()
                for mw in beat_middlewares:
                    try:
                        mw_ctx = mw.post_beat(beat_content.strip(), mw_ctx)
                    except Exception as e:
                        logger.debug(f"中间件 post_beat 异常（不影响主流程）: {e}")

                # 🔗 V2：节拍间衔接质量检查（零 LLM 调用，纯启发式）
                # 检测常见的节拍间割裂信号：对话断裂、跳跃词、情绪断裂
                if i > 0 and beat_content.strip():
                    try:
                        from application.engine.services.chapter_bridge_service import ChapterBridgeService
                        prior_parts = accumulated_content.rsplit("\n\n", 1)
                        prior_beat_text = prior_parts[0] if len(prior_parts) > 1 else ""
                        if prior_beat_text:
                            bridge_svc = ChapterBridgeService()
                            beat_score, beat_diag = await bridge_svc.check_beat_continuity(
                                novel.novel_id.value, chapter_num, i,
                                prior_beat_text, beat_content.strip(),
                            )
                            if beat_score < 0.6:
                                logger.warning(
                                    f"[{novel.novel_id}] 节拍衔接度低 "
                                    f"beat={i+1}/{len(beats)} score={beat_score:.2f} "
                                    f"diag={beat_diag}"
                                )
                                if i < len(beats) - 1:
                                    continuity_fix_hint = (
                                        f"\n\n【节拍衔接诊断】上一节拍衔接度={beat_score:.2f}，"
                                        f"问题：{beat_diag}。本节拍开头必须特别加强衔接！"
                                    )
                                    if not hasattr(novel, '_beat_continuity_hint'):
                                        novel._beat_continuity_hint = ""
                                    novel._beat_continuity_hint = continuity_fix_hint
                            else:
                                if hasattr(novel, '_beat_continuity_hint'):
                                    novel._beat_continuity_hint = ""
                    except Exception as e:
                        logger.debug(f"节拍衔接检查失败（不影响主流程）: {e}")

                # 🧠 V3 CoT 节拍桥接：在节拍完成后为下一节拍计算叙事状态桥接
                # 这使每两个节拍间有"思维链"衔接，确保正文不产生拼接感
                if i < len(beats) - 1 and beat_content.strip():
                    try:
                        from application.engine.services.beat_cot_bridge import compute_beat_bridge
                        next_beat = beats[i + 1]
                        next_intent = (next_beat.scene_goal or next_beat.description or "").strip()
                        if next_intent:
                            _bridge = await compute_beat_bridge(
                                beat_content.strip(),
                                next_intent,
                                chapter_outline=outline or "",
                            )
                            if _bridge:
                                _beat_cot_bridges[i + 1] = _bridge
                                logger.debug(
                                    "[%s] 节拍 %d→%d CoT 桥接完成: %r",
                                    novel.novel_id,
                                    i + 1,
                                    i + 2,
                                    _bridge.opening_line[:30] if _bridge.opening_line else "",
                                )
                    except Exception as _bridge_err:
                        logger.debug(f"[{novel.novel_id}] CoT 桥接计算跳过（不影响主流程）: {_bridge_err}")

                # AOF：追加写入 .draft 文件（无锁 append，崩溃恢复用）
                try:
                    from application.engine.services.draft_aof import append_chunk
                    append_chunk(novel.novel_id.value, chapter_num, "\n\n" + beat_content.strip() if accumulated_content != beat_content.strip() else beat_content.strip())
                except Exception:
                    pass  # AOF 失败不影响主流程

                # 批量写入（每 BATCH_WRITE_INTERVAL 个节拍或最后一个节拍时写入）
                if write_counter >= BATCH_WRITE_INTERVAL or i == len(beats) - 1:
                    # ★ 子步骤状态：批量持久化
                    host._update_shared_state(
                        novel.novel_id.value,
                        writing_substep="persisting",
                        writing_substep_label="节拍内容落盘",
                    )
                    await host._upsert_chapter_content(
                        novel, next_chapter_node, accumulated_content, status="draft"
                    )
                    write_counter = 0
                    logger.debug(f"[{novel.novel_id}] 批量写入，当前 {len(accumulated_content)} 字")

            # 更新内存中的节拍索引用于流式推送
            novel.current_beat_index = i + 1

            # 🔥 同步更新共享内存的节拍索引（不写 DB，纳秒级）
            # 这样前端 /status 可以实时看到进度，不会因为 DB 锁而阻塞
            host._update_shared_state(
                novel.novel_id.value,
                current_beat_index=i + 1,
                accumulated_words=len(accumulated_content),
            )

            # 如果是最后一个节拍，标记完成
            if i == len(beats) - 1:
                novel.beats_completed = True
                logger.info(f"[{novel.novel_id}] 所有节拍已完成，标记 beats_completed = True")

            # 更新流式元数据
            if hasattr(host, '_update_stream_metadata'):
                host._update_stream_metadata(novel.novel_id.value, i + 1, len(accumulated_content))

            logger.info(f"[{novel.novel_id}] 节拍 {i+1}/{len(beats)} 完成: {len(beat_content)} 字")

        # 循环结束后，使用累积的内容
        chapter_content = accumulated_content
    else:
        # 降级：无节拍，一次生成
        if not host._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止，跳过单段生成")
            return
        if use_wf:
            prompt = host.chapter_workflow.build_chapter_prompt(
                bundle["context"], outline,
                storyline_context=bundle["storyline_context"],
                plot_tension=bundle["plot_tension"],
                style_summary=bundle["style_summary"],
                voice_anchors=voice_anchors,
            )
            cfg = GenerationConfig(max_tokens=3000, temperature=0.85)
            beat_content = await host._stream_llm_with_stop_watch(
                prompt, cfg, novel=novel, chapter_draft_so_far=""
            )
        else:
            beat_content = await host._stream_one_beat(
                outline, context, None, None, novel=novel, voice_anchors=voice_anchors
            )
        if not host._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止，单段生成已中断")
            novel.current_beat_index = 0
            host._flush_novel(novel)
            return
        chapter_content = beat_content
        await host._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="draft")

    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止，本章不标记完成")
        host._flush_novel(novel)
        return

    if use_wf and chapter_content.strip():
        try:
            await host.chapter_workflow.post_process_generated_chapter(
                novel.novel_id.value, chapter_num, outline, chapter_content, scene_director=None
            )
            logger.info(f"[{novel.novel_id}] post_process_generated_chapter 完成")
        except Exception as e:
            logger.warning(f"post_process_generated_chapter 失败（仍落库）：{e}")

    # 7. 章节完成检查（弹性边界策略 —— 收紧：减少「章纲未写完就放行」）
    actual_word_count = len(chapter_content.strip())

    # 检测最后节拍是否是悬念收尾
    last_beat_is_suspense = beats and beats[-1].focus == "suspense" if beats else False

    # ★ Phase 3: 检测高能节拍是否存在（用于字数豁免）
    has_high_energy_beat = any(
        b.focus in ("action", "power_reveal", "identity_reveal", "hook", "cultivation")
        for b in (beats or [])
    )

    # ★ Phase 3: 计算节拍完成度（以 conductor 实际产出为准）
    # 断点续写时 conductor.beats 只含本轮执行的节拍，entry_start_beat 之前的节拍是之前轮次已完成的
    beats_completed_count = entry_start_beat + sum(1 for b in (conductor.beats or []) if b.actual > 0)
    total_beats_count = len(beats) if beats else 0
    beats_completion_ratio = beats_completed_count / max(total_beats_count, 1)

    # 检测内容是否完整（以句号等结束符结尾）
    import re
    ending_pattern = r'[。！？…）】》"\'』」]$'
    content_complete = bool(re.search(ending_pattern, chapter_content.strip()))

    # 主阈值：72% 以下视为「明显未写满」；88% 视为「字数达标」
    min_word_threshold = int(target_word_count * 0.72)
    good_word_threshold = int(target_word_count * 0.88)
    # 全节拍已跑完且句末完整时的绝对下限（避免极短篇误卡死，但仍高于旧 60%）
    exception_floor = int(target_word_count * 0.62)

    # 死锁检测：本轮入口时节拍索引已 >= 节拍总数，for 循环一个节拍都没跑，
    # 意味着系统无法产出任何新内容，若不强制放行将永远循环
    all_beats_exhausted_no_progress = (
        total_beats_count > 0
        and entry_start_beat >= total_beats_count
    )

    # 字数低于主阈值：默认不结章，续写；仅「全节拍有产出 + 句末完整 + ≥exception_floor」例外放行
    if actual_word_count < min_word_threshold:
        if (
            total_beats_count > 0
            and beats_completion_ratio >= 1.0
            and content_complete
            and actual_word_count >= exception_floor
        ):
            logger.info(
                f"[{novel.novel_id}] 收紧策略例外放行：全节拍已有产出且句末完整 "
                f"(字数 {actual_word_count}，约 {int(actual_word_count / target_word_count * 100)}%)"
            )
            should_complete = True
            completion_reason = (
                f"节拍完成+内容完整 (字数 {int(actual_word_count / target_word_count * 100)}%)"
            )
        elif all_beats_exhausted_no_progress and actual_word_count > 0:
            # 节拍已全部耗尽，本轮无法产出新内容。
            # 优先策略：清除现有 draft 内容，重置节拍索引，下一轮从第 0 拍重新生成。
            # 重试超过 2 次后退化为强制放行，避免无限循环。
            rewrite_key = (novel.novel_id.value, chapter_num)
            rewrite_count = host._beat_exhausted_rewrite_count.get(rewrite_key, 0)
            MAX_REWRITE = 2
            if rewrite_count < MAX_REWRITE:
                host._beat_exhausted_rewrite_count[rewrite_key] = rewrite_count + 1
                logger.warning(
                    f"[{novel.novel_id}] 第 {chapter_num} 章节拍已遍历完但字数不足 "
                    f"({actual_word_count}/{target_word_count})，"
                    f"清除 draft 内容并从第 0 拍重写（第 {rewrite_count + 1}/{MAX_REWRITE} 次）"
                )
                # 清除章节内容，让下一轮从零开始生成
                host._save_chapter_ephemeral(
                    novel.novel_id.value, chapter_num,
                    content="", status="draft", word_count=0
                )
                novel.current_beat_index = 0
                novel.beats_completed = False
                host._flush_novel(novel)
                return
            else:
                # 已重写 MAX_REWRITE 次仍不足，强制放行避免无限循环
                host._beat_exhausted_rewrite_count.pop(rewrite_key, None)
                logger.warning(
                    f"[{novel.novel_id}] 第 {chapter_num} 章已重写 {MAX_REWRITE} 次仍字数不足 "
                    f"({actual_word_count}/{target_word_count})，强制放行以打破死循环"
                )
                should_complete = True
                completion_reason = (
                    f"重写{MAX_REWRITE}次后强制放行 ({int(actual_word_count / target_word_count * 100)}%)"
                )
        else:
            logger.warning(
                f"[{novel.novel_id}] 第 {chapter_num} 章字数不足：{actual_word_count} 字 "
                f"(目标 {target_word_count} 字，低于 {int(min_word_threshold / target_word_count * 100)}%)"
            )
            # 保持 draft 状态，下一轮继续生成
            host._flush_novel(novel)
            logger.info(f"[{novel.novel_id}] 章节保持 draft 状态，下一轮尝试续写")
            return
    else:
        should_complete = False
        completion_reason = ""

    if not should_complete:
        # 字数达标：无节拍或节拍全部有产出才可放行（避免只写了前几拍就停）
        if actual_word_count >= good_word_threshold:
            if total_beats_count > 0 and beats_completion_ratio < 1.0:
                should_complete = False
                logger.warning(
                    f"[{novel.novel_id}] 第 {chapter_num} 章字数已高 "
                    f"({int(actual_word_count / target_word_count * 100)}%)，"
                    f"但节拍未全部产出 ({beats_completed_count}/{total_beats_count})，不结章"
                )
            else:
                should_complete = True
                completion_reason = f"字数达标 ({int(actual_word_count / target_word_count * 100)}%)"
        elif total_beats_count == 0 and content_complete and actual_word_count >= min_word_threshold:
            # 降级：无节拍拆分时仅看字数与句末完整
            should_complete = True
            completion_reason = f"单段生成+内容完整 ({int(actual_word_count / target_word_count * 100)}%)"
        elif (
            has_high_energy_beat
            and content_complete
            and actual_word_count >= min_word_threshold
            and beats_completion_ratio >= 1.0
        ):
            # 高能章：仍须写满全部节拍，且不低于 72%
            should_complete = True
            completion_reason = f"高能节拍+全拍完成+内容完整 ({int(actual_word_count / target_word_count * 100)}%)"
            logger.info(
                f"[{novel.novel_id}] 高能豁免放行：爽点章全拍完成，{actual_word_count} 字"
            )
        elif (
            last_beat_is_suspense
            and content_complete
            and actual_word_count >= min_word_threshold
            and beats_completion_ratio >= 1.0
        ):
            should_complete = True
            completion_reason = f"悬念收尾+全拍完成 ({int(actual_word_count / target_word_count * 100)}%)"
            logger.info(
                f"[{novel.novel_id}] 悬念章全拍完成放行，{actual_word_count} 字"
            )
        elif (
            beats_completion_ratio >= 1.0
            and content_complete
            and actual_word_count >= min_word_threshold
        ):
            should_complete = True
            completion_reason = f"节拍完成+内容完整 ({int(actual_word_count / target_word_count * 100)}%)"
            logger.info(
                f"[{novel.novel_id}] 弹性放行：所有节拍已有产出，{actual_word_count} 字"
            )

    if not should_complete:
        # 不满足放行条件，保持 draft 状态
        logger.warning(
            f"[{novel.novel_id}] 第 {chapter_num} 章未达到放行条件，保持 draft 状态"
        )
        host._flush_novel(novel)
        return

    # 8. 更新计数器，重置节拍状态
    novel.current_auto_chapters = (novel.current_auto_chapters or 0) + 1
    novel.current_chapter_in_act += 1
    novel.current_beat_index = 0
    novel.beats_completed = False  # 重置节拍完成标志
    nid = novel.novel_id.value
    if beats:
        host._pending_chapter_micro_beats[(nid, chapter_num)] = [
            {
                "description": b.description,
                "target_words": b.target_words,
                "focus": b.focus,
                "location_id": getattr(b, "location_id", "") or "",
            }
            for b in beats
        ]
    else:
        host._pending_chapter_micro_beats.pop((nid, chapter_num), None)
    novel.current_stage = NovelStage.AUDITING
    # 章节正常完成，清理对应的重写计数
    host._beat_exhausted_rewrite_count.pop((novel.novel_id.value, chapter_num), None)

    # 🔗 衔接引擎：章节完成后自检衔接度（非第 1 章）
    # 如果衔接度 < 0.6，自动修整首段（最多 2 轮）
    if chapter_num > 1:
        # ★ 子步骤状态：衔接自检
        host._update_shared_state(
            novel.novel_id.value,
            writing_substep="continuity_check",
            writing_substep_label="衔接度自检",
        )
        chapter_content = await host._continuity_self_check(
            novel.novel_id.value, chapter_num, chapter_content
        )

    # 🔥 先更新阶段到共享内存（不写章节聚合，避免占位 0 覆盖真实数据）
    host._update_shared_state(
        novel.novel_id.value,
        current_stage="auditing",
        current_auto_chapters=novel.current_auto_chapters,
        current_act=novel.current_act,
        current_chapter_in_act=novel.current_chapter_in_act,
        target_chapters=novel.target_chapters,
        target_words_per_chapter=novel.target_words_per_chapter,
        autopilot_status=novel.autopilot_status.value,
    )

    # 标记章节完成（DB 写入，可能阻塞）
    # ★ 子步骤状态：章节落盘
    host._update_shared_state(
        novel.novel_id.value,
        writing_substep="chapter_persist",
        writing_substep_label="章节落盘",
    )
    await host._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="completed")

    # 🔥 落库后用短连接读真实聚合，刷新 /status 缓存（与接口 SQL 一致）
    st = host._read_chapter_stats_ephemeral(novel.novel_id.value)
    if st:
        cc, mc, tw = st
        host._update_shared_state(
            novel.novel_id.value,
            _cached_completed_chapters=cc,
            _cached_manuscript_chapters=mc,
            _cached_total_words=tw,
            _cached_current_chapter_number=chapter_num,
        )

    # AOF：章节完成后删除 .draft 文件（数据已安全落盘到 DB）
    try:
        from application.engine.services.draft_aof import delete_draft
        delete_draft(novel.novel_id.value, chapter_num)
    except Exception:
        pass

    host._flush_novel(novel)

    logger.info(
        f"[{novel.novel_id}] 🎉 第 {chapter_num} 章完成：{actual_word_count} 字 "
        f"(目标 {target_word_count} 字，共 {novel.current_auto_chapters}/{novel.target_chapters} 章)"
    )

