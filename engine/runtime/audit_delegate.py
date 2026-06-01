"""章后审计委托 — Phase 5 从 AutopilotDaemon 迁入 engine/runtime"""
from __future__ import annotations

import logging
import hashlib
from datetime import datetime, timezone
from typing import Any

from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.generation_preferences import GenerationPreferences

logger = logging.getLogger(__name__)


async def run_chapter_audit(host: Any, novel: Novel) -> None:
    """处理审计（含张力打分）— host 提供基础设施 helper"""
    if not host._is_still_running(novel):
        return

    chapter_num = host._latest_completed_chapter_number(NovelId(novel.novel_id.value))
    if chapter_num is None:
        novel.current_stage = NovelStage.WRITING
        host._update_shared_state(
            novel.novel_id.value,
            current_stage="writing",
            audit_progress=None,
        )
        return

    chapter = host.chapter_repository.get_by_novel_and_number(
        NovelId(novel.novel_id.value), chapter_num
    )
    if not chapter:
        novel.current_stage = NovelStage.WRITING
        host._update_shared_state(
            novel.novel_id.value,
            current_stage="writing",
            audit_progress=None,
        )
        return

    content = chapter.content or ""
    original_content = content
    original_content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    host._sync_novel_current_act_from_chapter_number(novel, chapter_num)
    host._cache_stats_to_shared_memory(novel)
    chapter_id = ChapterId(chapter.id)

    # 🔥 发布审计开始事件
    host._publish_audit_event(
        novel.novel_id.value,
        "audit_start",
        {"chapter_number": chapter_num, "word_count": len(content)}
    )

    # 1. 先做文风预检；若严重偏离则定向改写，最多两轮，再执行章后管线，避免分析结果与最终正文错位
    novel.audit_progress = "voice_check"
    # 🔥 架构优化：写共享内存，零 DB IO
    host._update_shared_state(
        novel.novel_id.value,
        current_stage="auditing",
        audit_progress="voice_check",
        last_chapter_number=chapter_num,
        writing_substep="audit_voice_check",
        writing_substep_label="文风预检",
    )
    # 🔥 发布文风预检事件
    host._publish_audit_event(
        novel.novel_id.value,
        "audit_voice_check",
        {"chapter_number": chapter_num}
    )
    drift_result = await host._call_with_timeout(
        host._score_voice_only(novel.novel_id.value, chapter_num, content),
        timeout=180.0,  # 文风预检最多 3 分钟
        novel_id=novel.novel_id.value,
        label="voice_check",
        timeout_default={"drift_alert": False, "similarity_score": None},
    )
    content, drift_result = await host._apply_voice_rewrite_loop(
        novel,
        chapter,
        content,
        drift_result,
    )
    content_changed_by_audit = content != original_content
    # 🔥 发布文风预检结果事件
    host._publish_audit_event(
        novel.novel_id.value,
        "audit_voice_result",
        {
            "similarity_score": drift_result.get("similarity_score"),
            "drift_alert": drift_result.get("drift_alert"),
        }
    )

    # 2. 统一章后管线：叙事/向量、文风（一次）、KG 推断；三元组与伏笔在叙事同步单次 LLM 中落库
    novel.audit_progress = "aftermath_pipeline"
    # 🔥 架构优化：写共享内存，零 DB IO
    pending_aftermath = None
    pending_map = getattr(host, "_pending_story_pipeline_aftermath", None)
    if isinstance(pending_map, dict):
        pending_aftermath = pending_map.pop((novel.novel_id.value, chapter_num), None)

    can_reuse_aftermath = (
        isinstance(pending_aftermath, dict)
        and not content_changed_by_audit
        and pending_aftermath.get("content_sha256") == original_content_sha256
    )
    should_rebuild_aftermath = not can_reuse_aftermath and content_changed_by_audit
    aftermath_label = (
        "结果复用"
        if can_reuse_aftermath
        else ("章后重建" if should_rebuild_aftermath else "章后校准")
    )

    host._update_shared_state(
        novel.novel_id.value,
        audit_progress="aftermath_pipeline",
        writing_substep="audit_aftermath",
        writing_substep_label=aftermath_label,
        audit_aftermath_reused=can_reuse_aftermath,
        audit_aftermath_rebuilt=should_rebuild_aftermath,
    )
    # 🔥 发布章后管线事件
    host._publish_audit_event(
        novel.novel_id.value,
        "audit_aftermath",
        {
            "chapter_number": chapter_num,
            "reused": can_reuse_aftermath,
            "rebuilt": should_rebuild_aftermath,
        }
    )
    if can_reuse_aftermath:
        audit_similarity = drift_result.get("similarity_score")
        drift_result = {
            **pending_aftermath,
            "similarity_score": audit_similarity
            if audit_similarity is not None
            else pending_aftermath.get("similarity_score"),
            "drift_alert": bool(
                drift_result.get("drift_alert", pending_aftermath.get("drift_alert", False))
            ),
            "reused": True,
        }
        logger.info(
            "[%s] 章后管线复用 StoryPipeline 第 8 步结果：第%s章",
            novel.novel_id.value,
            chapter_num,
        )
    elif host.aftermath_pipeline:
        try:
            _mb = host._pending_chapter_micro_beats.pop(
                (novel.novel_id.value, chapter_num), None
            )
            drift_result = await host._call_with_timeout(
                host.aftermath_pipeline.run_after_chapter_saved(
                    novel.novel_id.value,
                    chapter_num,
                    content,
                    chapter_micro_beats=_mb,
                ),
                timeout=300.0,  # 章后管线最多 5 分钟（含多次 LLM）
                novel_id=novel.novel_id.value,
                label="aftermath_pipeline",
                timeout_default={"drift_alert": False, "similarity_score": None, "narrative_sync_ok": False, "vector_stored": False, "foreshadow_stored": False, "triples_extracted": False},
            )
            logger.info(
                f"[{novel.novel_id}] 章后管线完成: 相似度={drift_result.get('similarity_score')}, "
                f"drift_alert={drift_result.get('drift_alert')}"
            )
        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 章后管线失败（降级旧逻辑）：{e}")
            drift_result = host._legacy_auditing_tasks_and_voice(
                novel, chapter_num, content, chapter_id
            )
    else:
        drift_result = host._legacy_auditing_tasks_and_voice(
            novel, chapter_num, content, chapter_id
        )

    # ── 停止检查：章后管线和文风预检完成后 ──
    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止（章后管线完成后），跳过张力打分")
        return

    # 2. 张力打分（轻量 LLM 调用，~200 token）
    novel.audit_progress = "tension_scoring"
    # 🔥 架构优化：写共享内存，零 DB IO
    host._update_shared_state(
        novel.novel_id.value,
        audit_progress="tension_scoring",
        writing_substep="audit_tension",
        writing_substep_label="张力打分",
    )
    # 🔥 发布张力打分事件
    host._publish_audit_event(
        novel.novel_id.value,
        "audit_tension",
        {"chapter_number": chapter_num}
    )
    # ★ Phase 1: 统一张力刻度为 0-100（不再有损转换为 1-10）
    # 优先使用章后管线中的多维张力评分（0-100），替代旧式 _score_tension（1-10）
    tension_composite = drift_result.get("tension_composite") if drift_result else None
    if tension_composite is not None and tension_composite > 0:
        tension = int(tension_composite)  # 直接存 0-100，不再 /10 降级
        logger.info(f"[{novel.novel_id}] 章节 {chapter_num} 多维张力值：{tension}/100")
    else:
        # 降级：旧式评分（1-10），升级到 0-100 刻度
        old_scale_tension = await host._call_with_timeout(
            host._score_tension(content),
            timeout=60.0,
            novel_id=novel.novel_id.value,
            label="tension_scoring",
            timeout_default=5,
        )
        tension = old_scale_tension * 10  # 1-10 → 0-100
        logger.info(f"[{novel.novel_id}] 章节 {chapter_num} 旧式张力值：{old_scale_tension}/10 → {tension}/100")
    novel.last_chapter_tension = tension
    # 共享内存：供 /status 等高频读路径；章节张力另见下方 _write_tension_ephemeral
    host._update_shared_state(
        novel.novel_id.value,
        last_chapter_tension=tension,
    )
    # 同步章节张力到 chapters 表，供 /monitor/tension-curve 与「audit_tension_result」SSE 刷新一致读库
    #（章后管线可能已写过多维张力，此处幂等 UPDATE 覆盖 composite；旧式打分路径则依赖本次写入）
    try:
        from application.world.services.chapter_narrative_sync import _write_tension_ephemeral

        _write_tension_ephemeral(
            novel.novel_id.value, chapter_num, float(tension), None
        )
    except Exception as e:
        logger.debug(
            "[%s] 张力同步 chapters 表失败（非致命）: %s",
            novel.novel_id.value,
            e,
        )
    # 🔥 发布张力打分结果事件
    host._publish_audit_event(
        novel.novel_id.value,
        "audit_tension_result",
        {"tension": tension, "chapter_number": chapter_num}
    )
    logger.info(f"[{novel.novel_id}] 章节 {chapter_num} 张力值：{tension}/100（共享内存 + 章节表已对齐）")

    # 章末审阅快照（写入 novels，供 /autopilot/status 与前台「章节状态 / 章节元素」）
    previous_same_chapter_drift = (
        novel.last_audit_chapter_number == chapter_num
        and bool(novel.last_audit_drift_alert)
    )
    novel.last_audit_chapter_number = chapter_num
    novel.last_audit_similarity = drift_result.get("similarity_score")
    novel.last_audit_drift_alert = bool(drift_result.get("drift_alert", False))
    novel.last_audit_narrative_ok = bool(drift_result.get("narrative_sync_ok", True))
    novel.last_audit_vector_stored = bool(drift_result.get("vector_stored", False))
    novel.last_audit_foreshadow_stored = bool(drift_result.get("foreshadow_stored", False))
    novel.last_audit_triples_extracted = bool(drift_result.get("triples_extracted", False))
    novel.last_audit_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    drift_too_high = bool(drift_result.get("drift_alert", False))
    similarity_score = drift_result.get("similarity_score")
    similarity_below_threshold = host._similarity_below_warning_threshold(similarity_score)
    if drift_result.get("similarity_score") is not None:
        logger.info(
            f"[{novel.novel_id}] 文风相似度：{drift_result.get('similarity_score')}，"
            f"告警：{drift_too_high}"
        )

    # 3. 文风漂移仅保留告警，不再删章回滚
    if drift_too_high and similarity_below_threshold:
        logger.warning(
            f"[{novel.novel_id}] 章节 {chapter_num} 文风仍偏离，但已完成有限次定向修正，保留本章继续推进"
        )
    elif drift_too_high and previous_same_chapter_drift:
        logger.info(
            f"[{novel.novel_id}] 同章文风告警持续存在，但已从删除回滚切换为保留并继续"
        )
    elif drift_too_high and not similarity_below_threshold:
        logger.info(
            f"[{novel.novel_id}] 文风告警来自历史窗口，当前章节相似度未低于阈值，保留本章"
        )

    # ── 停止检查：张力打分完成后 ──
    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止（张力打分完成后），跳过落库")
        return

    # 🛡️ Anti-AI：在章末闸门判定之前执行（结果落库），以便「严重」可触发 paused_for_review
    anti_report = await host._run_anti_ai_audit(
        novel.novel_id.value, chapter_num, content
    )

    prefs = getattr(novel, "generation_prefs", None) or GenerationPreferences()
    auto = bool(getattr(novel, "auto_approve_mode", False))

    hard_narrative = not bool(drift_result.get("narrative_sync_ok", True))
    hard_voice = drift_too_high and similarity_below_threshold
    hard_fail = hard_narrative or hard_voice

    anti_assessment = None
    if anti_report is not None:
        anti_assessment = getattr(
            getattr(anti_report, "metrics", None), "overall_assessment", None
        )
    anti_ai_severe = anti_assessment == "严重"

    pause_gate = (not auto) and (
        bool(getattr(prefs, "pause_after_each_chapter_audit", False))
        or (
            bool(getattr(prefs, "audit_pause_on_hard_fail", False))
            and hard_fail
        )
        or (
            bool(getattr(prefs, "audit_pause_on_anti_ai_severe", False))
            and anti_ai_severe
        )
    )

    novel.audit_progress = None  # 审计完成，清除进度标记
    novel.current_beat_index = 0  # 🔥 重置节拍索引，下一章从节拍 0 开始
    novel.beats_completed = False  # 🔥 重置节拍完成标志

    # 5. 全书完成检测（用轻量 COUNT 查询替代 list_by_novel，减少 DB 锁持有时间）
    completed_count = host._count_completed_chapters(NovelId(novel.novel_id.value))
    book_done = completed_count >= novel.target_chapters

    if pause_gate:
        novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
        logger.info(
            "[%s] 章末审阅闸门：进入 paused_for_review（每章一停=%s，硬伤停机=%s，Anti-AI严重=%s；"
            "narrative_ok=%s hard_voice=%s assessment=%s）",
            novel.novel_id.value,
            getattr(prefs, "pause_after_each_chapter_audit", False),
            bool(getattr(prefs, "audit_pause_on_hard_fail", False)) and hard_fail,
            bool(getattr(prefs, "audit_pause_on_anti_ai_severe", False))
            and anti_ai_severe,
            drift_result.get("narrative_sync_ok", True),
            hard_voice,
            anti_assessment,
        )
    else:
        novel.current_stage = NovelStage.WRITING

    if book_done and not pause_gate:
        logger.info(f"[{novel.novel_id}] 全书完成，共 {completed_count} 章")
        novel.autopilot_status = AutopilotStatus.STOPPED
        novel.current_stage = NovelStage.COMPLETED
    elif book_done and pause_gate:
        logger.info(
            "[%s] 全书已完成 %s 章，但章末闸门打开：保持待审阅，恢复后继续结束流程",
            novel.novel_id.value,
            completed_count,
        )

    # 🔥 发布审计完成事件
    host._publish_audit_event(
        novel.novel_id.value,
        "audit_complete",
        {
            "chapter_number": chapter_num,
            "tension": tension,
            "similarity_score": drift_result.get("similarity_score"),
            "completed_chapters": completed_count,
            "target_chapters": novel.target_chapters,
            "is_completed": book_done and not pause_gate,
            "paused_for_review": pause_gate,
            "hard_fail": hard_fail,
            "anti_ai_assessment": anti_assessment,
        },
    )

    # 🔥 审计完成：统一 save 到 DB（低频、一次落盘）
    # 同时更新共享内存，让前端立刻感知
    st_stats = host._read_chapter_stats_ephemeral(novel.novel_id.value)
    if st_stats:
        cc_sig, mc_sig, tw_sig = st_stats
    else:
        cc_sig, mc_sig, tw_sig = completed_count, completed_count, 0

    host._update_shared_state(
        novel.novel_id.value,
        current_stage=novel.current_stage.value,
        audit_progress=None,
        current_beat_index=0,  # 🔥 同步重置节拍索引到共享内存
        current_auto_chapters=novel.current_auto_chapters,  # 🔥 同步已完成章节数
        last_audit_chapter_number=novel.last_audit_chapter_number,
        last_audit_similarity=novel.last_audit_similarity,
        last_audit_drift_alert=novel.last_audit_drift_alert,
        last_audit_narrative_ok=novel.last_audit_narrative_ok,
        last_audit_vector_stored=novel.last_audit_vector_stored,
        last_audit_foreshadow_stored=novel.last_audit_foreshadow_stored,
        last_audit_triples_extracted=novel.last_audit_triples_extracted,
        last_audit_causal_edges_stored=bool(drift_result.get("causal_edges_stored", False)),
        last_audit_character_mutations_stored=bool(drift_result.get("character_mutations_stored", False)),
        last_audit_debt_updated=bool(drift_result.get("debt_updated", False)),
        last_audit_at=novel.last_audit_at,
        last_chapter_tension=novel.last_chapter_tension,
        _cached_completed_chapters=cc_sig,
        _cached_manuscript_chapters=mc_sig,
        _cached_total_words=tw_sig,
        target_chapters=novel.target_chapters,
        target_words_per_chapter=novel.target_words_per_chapter,
        autopilot_status=novel.autopilot_status.value,
        consecutive_error_count=novel.consecutive_error_count,
    )

    # 🔥 审计完成时：不再用旧式 _score_tension (1-10) 写入 chapters.tension_score
    # 原因：章后管线（chapter_narrative_sync）已通过 TensionScoringService 进行多维评分
    # （0-100 刻度，含 plot/emotional/pacing），并通过 _write_tension_ephemeral 写入 DB。
    # 旧式评分仅取前500字、1-10 粗粒度，会覆盖真实多维评分，导致张力图变平。
    # ★ Phase 1: novel.last_chapter_tension 已统一为 0-100 刻度，用于余韵章判断。

    # 🔥 核心修复：novel_repository.save() 改为独立短连接写入
    # 原因：repository.save() 使用线程本地长连接，写锁持有时间不可控
    # 在守护进程（multiprocessing.Process）中，这会阻塞 API 进程的所有 DB 操作
    host._save_novel_ephemeral(novel)
    logger.info(f"[{novel.novel_id}] 审计完成，状态已落盘")

    # 🔥 审计完成：同步编年史+故事线到共享内存
    # narrative_sync 会更新故事线进度到 DB，这里重新加载确保共享内存同步
    host._sync_chronicles_to_shared_memory(novel.novel_id.value)
    host._sync_storylines_to_shared_memory(novel.novel_id.value)

    # 🔗 衔接引擎：审计完成后提取章节桥段（供下一章首段衔接使用）
    await host._extract_chapter_bridge(novel.novel_id.value, chapter_num, content)

    # ── 停止检查：审计落盘完成后 ──
    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止（审计落盘后），跳过摘要生成")
        return

    # 6. 自动触发宏观诊断（卷完结或约 6 万字间隔；静默注入，无前端提案交互）
    await host._auto_trigger_macro_diagnosis(novel, completed_count)

    # ── 停止检查：宏观诊断完成后 ──
    if not host._is_still_running(novel):
        logger.info(f"[{novel.novel_id}] 用户已停止（宏观诊断后），跳过摘要生成")
        return

    # 7. 🆕 摘要生成钩子（双轨融合 - 轨道一）
    await host._maybe_generate_summaries(novel, completed_count)

