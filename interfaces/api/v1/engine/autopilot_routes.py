"""自动驾驶控制 API（v2：含审阅确认 + SSE 生成流）"""
import asyncio
import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from domain.novel.entities.novel import AutopilotStatus, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from interfaces.api.dependencies import get_novel_repository, get_chapter_repository
from application.paths import get_db_path
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

logger = logging.getLogger(__name__)


def _has_chapter_nodes_under_current_act(novel_id: str, current_act_zero_based: int) -> bool:
    """当前幕（0-based）下是否已有章节结构节点。有则确认审阅后应直接 WRITING，避免再次跑幕级规划并重复弹确认。"""
    repo = StoryNodeRepository(get_db_path())
    target_act_number = (current_act_zero_based or 0) + 1
    all_nodes = repo.get_by_novel_sync(novel_id)
    act_nodes = sorted(
        [
            n
            for n in all_nodes
            if (n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type)) == "act"
        ],
        key=lambda n: n.number,
    )
    target = next((n for n in act_nodes if n.number == target_act_number), None)
    if not target:
        return False
    for ch in repo.get_children_sync(target.id):
        t = ch.node_type.value if hasattr(ch.node_type, "value") else str(ch.node_type)
        if t == "chapter":
            return True
    return False


def _stage_after_review(novel) -> NovelStage:
    """审阅确认后的下一阶段：幕下已有章节点 → 写作；否则 → 幕级规划（含宏观审阅后尚未规划章节的情况）。"""
    nid = novel.novel_id.value if hasattr(novel.novel_id, "value") else str(novel.novel_id)
    ca = getattr(novel, "current_act", 0) or 0
    if _has_chapter_nodes_under_current_act(nid, ca):
        return NovelStage.WRITING
    return NovelStage.ACT_PLANNING
router = APIRouter(prefix="/autopilot", tags=["autopilot"])

# 与 AutopilotDaemon 中单本挂起阈值一致；守护进程内另有全局 CircuitBreaker（独立进程，API 不可见）
PER_NOVEL_FAILURE_THRESHOLD = 3


def _stage_name_zh(stage: str) -> str:
    """阶段枚举值 → 中文（与前端驾驶舱一致）"""
    m = {
        "planning": "规划（旧）",
        "macro_planning": "宏观规划",
        "act_planning": "幕级规划",
        "writing": "正文撰写",
        "auditing": "章节审计",
        "reviewing": "审阅（旧）",
        "paused_for_review": "待审阅确认",
        "completed": "全书完成",
    }
    return m.get(stage, stage)


def _autopilot_status_zh(status: str) -> str:
    return {
        "stopped": "已停止",
        "running": "运行中",
        "error": "异常挂起",
        "completed": "已完成",
    }.get(status, status)


class StartRequest(BaseModel):
    max_auto_chapters: Optional[int] = 9999  # 保护上限，默认几乎无限制，由 target_chapters 控制实际完成点


@router.post("/{novel_id}/start")
async def start_autopilot(novel_id: str, body: StartRequest = StartRequest()):
    """启动自动驾驶"""
    repo = get_novel_repository()
    novel = repo.get_by_id(NovelId(novel_id))
    if not novel:
        raise HTTPException(404, "小说不存在")

    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.max_auto_chapters = body.max_auto_chapters
    novel.current_auto_chapters = novel.current_auto_chapters or 0
    novel.consecutive_error_count = 0

    # 如果是全新小说，从宏观规划开始
    fresh_stages = {NovelStage.PLANNING, NovelStage.MACRO_PLANNING}
    if novel.current_stage in fresh_stages:
        novel.current_stage = NovelStage.MACRO_PLANNING

    # 如果之前处于审阅等待：幕下已有章节节点则直接写作，否则幕级规划（避免重复弹确认）
    if novel.current_stage == NovelStage.PAUSED_FOR_REVIEW:
        novel.current_stage = _stage_after_review(novel)

    repo.save(novel)
    return {
        "success": True,
        "message": f"自动驾驶已启动，目标 {novel.target_chapters} 章（保护上限 {body.max_auto_chapters} 章）",
        "autopilot_status": novel.autopilot_status.value,
        "current_stage": novel.current_stage.value,
        "target_chapters": novel.target_chapters,
    }


@router.post("/{novel_id}/stop")
async def stop_autopilot(novel_id: str):
    """停止自动驾驶"""
    repo = get_novel_repository()
    novel = repo.get_by_id(NovelId(novel_id))
    if not novel:
        raise HTTPException(404, "小说不存在")
    novel.autopilot_status = AutopilotStatus.STOPPED
    repo.save(novel)
    logger.info("autopilot stop: novel_id=%s committed STOPPED", novel_id)
    return {"success": True, "message": "自动驾驶已停止"}


@router.post("/{novel_id}/resume")
async def resume_from_review(novel_id: str):
    """从人工审阅点恢复（PAUSED_FOR_REVIEW → RUNNING）"""
    repo = get_novel_repository()
    novel = repo.get_by_id(NovelId(novel_id))
    if not novel:
        raise HTTPException(404, "小说不存在")
    if novel.current_stage != NovelStage.PAUSED_FOR_REVIEW:
        raise HTTPException(400, f"当前不在审阅等待状态（当前：{novel.current_stage.value}）")

    novel.autopilot_status = AutopilotStatus.RUNNING
    next_stage = _stage_after_review(novel)
    novel.current_stage = next_stage
    repo.save(novel)
    if next_stage == NovelStage.WRITING:
        msg = "已恢复：当前幕已有章节规划，进入正文撰写"
    else:
        msg = "已恢复：继续幕级规划"
    logger.info("autopilot resume novel=%s -> %s", novel_id, next_stage.value)
    return {"success": True, "message": msg, "current_stage": novel.current_stage.value}


@router.get("/{novel_id}/status")
async def get_autopilot_status(novel_id: str):
    """获取完整运行状态"""
    novel_repo = get_novel_repository()
    chapter_repo = get_chapter_repository()

    novel = novel_repo.get_by_id(NovelId(novel_id))
    if not novel:
        raise HTTPException(404, "小说不存在")

    chapters = chapter_repo.list_by_novel(NovelId(novel_id))
    total_words = sum(
        c.word_count.value if hasattr(c.word_count, 'value') else c.word_count
        for c in chapters if c.word_count
    )
    _status = lambda c: c.status.value if hasattr(c.status, 'value') else c.status
    completed = [c for c in chapters if _status(c) == "completed"]
    in_manuscript = [c for c in chapters if _status(c) in ("draft", "completed")]
    target = novel.target_chapters or 1

    lacn = getattr(novel, "last_audit_chapter_number", None)
    last_chapter_audit = None
    if lacn is not None:
        last_chapter_audit = {
            "chapter_number": int(lacn),
            "tension": int(getattr(novel, "last_chapter_tension", 0) or 0),
            "drift_alert": bool(getattr(novel, "last_audit_drift_alert", False)),
            "similarity_score": getattr(novel, "last_audit_similarity", None),
            "narrative_sync_ok": bool(getattr(novel, "last_audit_narrative_ok", True)),
            "at": getattr(novel, "last_audit_at", None),
            # 章后管线状态
            "vector_stored": bool(getattr(novel, "last_audit_vector_stored", False)),
            "foreshadow_stored": bool(getattr(novel, "last_audit_foreshadow_stored", False)),
            "triples_extracted": bool(getattr(novel, "last_audit_triples_extracted", False)),
            "quality_scores": getattr(novel, "last_audit_quality_scores", {}) or {},
            "issues": getattr(novel, "last_audit_issues", []) or [],
        }

    return {
        "autopilot_status": novel.autopilot_status.value,
        "current_stage": novel.current_stage.value,
        "current_act": novel.current_act,
        "current_chapter_in_act": novel.current_chapter_in_act,
        "current_beat_index": getattr(novel, "current_beat_index", 0),
        "current_auto_chapters": getattr(novel, "current_auto_chapters", 0),
        "max_auto_chapters": getattr(novel, "max_auto_chapters", 9999),
        "target_chapters": novel.target_chapters,
        "last_chapter_tension": getattr(novel, "last_chapter_tension", 0),
        "consecutive_error_count": getattr(novel, "consecutive_error_count", 0),
        "total_words": total_words,
        "completed_chapters": len(completed),
        "progress_pct": round(len(completed) / target * 100, 1) if target else 0,
        "manuscript_chapters": len(in_manuscript),
        "progress_pct_manuscript": round(len(in_manuscript) / target * 100, 1) if target else 0,
        "needs_review": novel.current_stage.value == "paused_for_review",
        "auto_approve_mode": getattr(novel, "auto_approve_mode", False),
        "last_chapter_audit": last_chapter_audit,
    }


@router.get("/{novel_id}/circuit-breaker")
async def get_circuit_breaker(novel_id: str):
    """
    熔断面板数据：基于小说落库的连续失败计数与自动驾驶状态。
    （守护进程内的全局熔断器无法跨进程读取，此处不反映 API 级熔断。）
    """
    repo = get_novel_repository()
    novel = repo.get_by_id(NovelId(novel_id))
    if not novel:
        raise HTTPException(404, "小说不存在")

    error_count = getattr(novel, "consecutive_error_count", 0) or 0
    ap = novel.autopilot_status

    if ap == AutopilotStatus.ERROR:
        breaker_status = "open"
    elif ap == AutopilotStatus.RUNNING and 0 < error_count < PER_NOVEL_FAILURE_THRESHOLD:
        breaker_status = "half_open"
    else:
        breaker_status = "closed"

    return {
        "status": breaker_status,
        "error_count": error_count,
        "max_errors": PER_NOVEL_FAILURE_THRESHOLD,
        "last_error": None,
        "error_history": [],
    }


@router.post("/{novel_id}/circuit-breaker/reset")
async def reset_circuit_breaker(novel_id: str):
    """清零连续失败计数；若因错误挂起则切回停止，需用户重新启动自动驾驶。"""
    repo = get_novel_repository()
    novel = repo.get_by_id(NovelId(novel_id))
    if not novel:
        raise HTTPException(404, "小说不存在")

    novel.consecutive_error_count = 0
    if novel.autopilot_status == AutopilotStatus.ERROR:
        novel.autopilot_status = AutopilotStatus.STOPPED
    repo.save(novel)
    return {"success": True, "message": "熔断计数已清零"}


@router.get("/{novel_id}/stream")
async def autopilot_log_stream(novel_id: str):
    """
    SSE 实时日志流（用于监控大盘）

    推送 beat 级别的事件日志：
    - beat_start: 开始生成某个 beat
    - beat_complete: beat 生成完成
    - beat_error: beat 生成失败
    - stage_change: 阶段变更
    """
    novel_repo = get_novel_repository()
    chapter_repo = get_chapter_repository()

    async def event_generator():
        def _resolve_current_chapter_number(novel) -> Optional[int]:
            """
            日志流事件补齐“当前章节号”。
            由于 Novel 表仅存 current_act/current_chapter_in_act（非全书章号），这里从章节表推断：
            - 若有 draft 章：取最大 draft 章号（通常就是正在生成的那章，节拍级增量落库）
            - 否则：取最大 completed 章号 + 1（作为“即将写入”的预测章号）
            """
            try:
                chapters = chapter_repo.list_by_novel(NovelId(novel_id))
                _st = lambda c: c.status.value if hasattr(c.status, "value") else c.status
                drafts = [c for c in chapters if _st(c) == "draft"]
                if drafts:
                    return max(int(c.number) for c in drafts)
                completed = [c for c in chapters if _st(c) == "completed"]
                if completed:
                    return max(int(c.number) for c in completed) + 1
            except Exception:
                return None
            return None

        # 发送初始连接事件
        init_event = {
            "type": "connected",
            "message": "日志流已连接（阶段变更需连续约 4 秒一致才推送，避免界面抖动）",
            "timestamp": datetime.now().isoformat()
        }
        yield f"data: {json.dumps(init_event, ensure_ascii=False)}\n\n"

        last_beat = None
        heartbeat_counter = 0
        last_error_broadcast = -1
        # 阶段变更去抖：同一阶段需连续 2 次轮询（约 4s）一致才推送，避免幕级规划↔待审阅 来回刷屏
        first_stage_poll = True
        last_emitted_stage: Optional[str] = None
        stage_pending: Optional[str] = None
        stage_pending_ticks = 0

        while True:
            try:
                novel = novel_repo.get_by_id(NovelId(novel_id))
                if not novel:
                    break

                current_stage = novel.current_stage.value
                current_beat = getattr(novel, "current_beat_index", 0)
                current_chapter_number = _resolve_current_chapter_number(novel)
                chapter_label = f"第 {current_chapter_number} 章 · " if current_chapter_number else ""

                # 检测阶段变更（去抖后推送）
                if first_stage_poll:
                    last_emitted_stage = current_stage
                    first_stage_poll = False
                elif current_stage == last_emitted_stage:
                    stage_pending = None
                    stage_pending_ticks = 0
                else:
                    if stage_pending != current_stage:
                        stage_pending = current_stage
                        stage_pending_ticks = 1
                    else:
                        stage_pending_ticks += 1
                    if stage_pending_ticks >= 2 and current_stage != last_emitted_stage:
                        from_zh = _stage_name_zh(last_emitted_stage or current_stage)
                        to_zh = _stage_name_zh(current_stage)
                        event = {
                            "type": "stage_change",
                            "message": f"阶段变更：{from_zh} → {to_zh}",
                            "timestamp": datetime.now().isoformat(),
                            "metadata": {
                                "from_stage": last_emitted_stage,
                                "to_stage": current_stage,
                                "from_label": from_zh,
                                "to_label": to_zh,
                            },
                        }
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        last_emitted_stage = current_stage
                        stage_pending = None
                        stage_pending_ticks = 0

                # 检测 beat 变更（表示上一个 beat 完成）
                act_display = (novel.current_act or 0) + 1
                if last_beat is not None and current_beat > last_beat:
                    event = {
                        "type": "beat_complete",
                        "message": f"{chapter_label}第 {act_display} 幕 · 节拍 {last_beat} 已生成完毕",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "beat_index": last_beat,
                            "act": novel.current_act,
                            "act_display": act_display,
                            "chapter_number": current_chapter_number,
                        },
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                    # 新 beat 开始
                    event = {
                        "type": "beat_start",
                        "message": f"{chapter_label}第 {act_display} 幕 · 正在生成节拍 {current_beat}",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "beat_index": current_beat,
                            "act": novel.current_act,
                            "act_display": act_display,
                            "chapter_number": current_chapter_number,
                        },
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 检测错误（仅在计数变化时推送，避免每 2 秒刷屏）
                error_count = getattr(novel, "consecutive_error_count", 0) or 0
                if error_count > 0 and error_count != last_error_broadcast:
                    last_error_broadcast = error_count
                    if error_count >= 3:
                        err_msg = (
                            f"连续失败已达 {error_count} 次，本书可能被标为异常并停止；"
                            "请在驾驶舱「解除挂起并清零计数」后重试，并确认守护进程与 LLM 可用。"
                        )
                    else:
                        err_msg = (
                            f"记录到连续失败 {error_count} 次（满 3 次将挂起）。"
                            "若持续出现，请检查模型/API 与守护进程日志。"
                        )
                    event = {
                        "type": "beat_error",
                        "message": err_msg,
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {"error_count": error_count},
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if error_count == 0:
                    last_error_broadcast = -1

                last_beat = current_beat

                # 终止条件
                terminal_states = {"stopped", "error", "completed"}
                if novel.autopilot_status.value in terminal_states:
                    st = novel.autopilot_status.value
                    event = {
                        "type": "autopilot_complete",
                        "message": f"自动驾驶{_autopilot_status_zh(st)}",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "status": st,
                            "status_label": _autopilot_status_zh(st),
                        },
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    break

                # 运行中：定期推送进度快照（仅用于前端进度条，不写时间线刷屏）
                if novel.autopilot_status.value == AutopilotStatus.RUNNING.value:
                    chapters = chapter_repo.list_by_novel(NovelId(novel_id))
                    _st = lambda c: c.status.value if hasattr(c.status, "value") else c.status
                    completed = [c for c in chapters if _st(c) == "completed"]
                    drafts = [c for c in chapters if _st(c) == "draft"]
                    n_done = len(completed)
                    tgt = novel.target_chapters or 1
                    pct = round(n_done / tgt * 100, 1) if tgt else 0.0
                    total_words = sum(
                        c.word_count.value if hasattr(c.word_count, "value") else c.word_count
                        for c in chapters
                        if c.word_count
                    )
                    stage_zh = _stage_name_zh(current_stage)
                    act_display = (novel.current_act or 0) + 1
                    tw = int(total_words) if total_words else 0
                    current_chapter_number = None
                    try:
                        if drafts:
                            current_chapter_number = max(int(c.number) for c in drafts)
                        elif completed:
                            current_chapter_number = max(int(c.number) for c in completed) + 1
                    except Exception:
                        current_chapter_number = None
                    progress_event = {
                        "type": "progress",
                        "message": (
                            f"全书 {n_done}/{tgt} 章 · 约 {tw} 字 · "
                            f"第 {act_display} 幕 · 节拍 {current_beat} · {stage_zh}"
                        ),
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "completed_chapters": n_done,
                            "target_chapters": tgt,
                            "progress_pct": pct,
                            "total_words": total_words,
                            "current_act": novel.current_act,
                            "act_display": act_display,
                            "current_beat_index": current_beat,
                            "stage": current_stage,
                            "stage_label": stage_zh,
                            "chapter_number": current_chapter_number,
                        },
                    }
                    yield f"data: {json.dumps(progress_event, ensure_ascii=False)}\n\n"

                # 每 10 次循环（20秒）发送一次心跳
                heartbeat_counter += 1
                if heartbeat_counter >= 10:
                    heartbeat_event = {
                        "type": "heartbeat",
                        "message": "keepalive",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(heartbeat_event, ensure_ascii=False)}\n\n"
                    heartbeat_counter = 0

                await asyncio.sleep(2)  # 每2秒检查一次

            except Exception as e:
                logger.error(f"SSE log stream error: {e}")
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/{novel_id}/chapter-stream")
async def autopilot_chapter_stream(novel_id: str):
    """SSE 实时推送正在写作的章节内容（真正的流式）

    推送事件类型：
    - chapter_content: 增量文字片段
    - chapter_complete: 章节写作完成
    - chapter_start: 开始写新章节
    """
    novel_repo = get_novel_repository()
    chapter_repo = get_chapter_repository()

    async def event_generator():
        from application.engine.services.streaming_bus import streaming_bus

        # 发送初始连接事件
        init_event = {
            "type": "connected",
            "message": "章节内容流已连接",
            "timestamp": datetime.now().isoformat()
        }
        yield f"data: {json.dumps(init_event, ensure_ascii=False)}\n\n"

        last_chapter_number = None
        heartbeat_counter = 0

        try:
            while True:
                # 检查自动驾驶状态
                novel = novel_repo.get_by_id(NovelId(novel_id))
                if not novel:
                    break

                terminal_states = {"stopped", "error", "completed"}
                if novel.autopilot_status.value in terminal_states:
                    event = {
                        "type": "autopilot_stopped",
                        "message": f"自动驾驶已停止: {novel.autopilot_status.value}",
                        "timestamp": datetime.now().isoformat(),
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    break

                # 检测新章节开始
                if novel.current_stage.value == "writing":
                    chapters = chapter_repo.list_by_novel(NovelId(novel_id))
                    _st = lambda c: c.status.value if hasattr(c.status, "value") else c.status
                    drafts = sorted(
                        [c for c in chapters if _st(c) == "draft"],
                        key=lambda c: c.number
                    )
                    if drafts:
                        chapter_number = drafts[0].number
                        # 发送章节开始事件（首次或章节改变时）
                        if last_chapter_number is None or chapter_number != last_chapter_number:
                            event = {
                                "type": "chapter_start",
                                "message": f"开始写第 {chapter_number} 章",
                                "timestamp": datetime.now().isoformat(),
                                "metadata": {"chapter_number": chapter_number},
                            }
                            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                            logger.debug(f"[SSE] 发送 chapter_start: 第 {chapter_number} 章, novel={novel_id}")
                            streaming_bus.clear(novel_id)  # 清空旧内容
                        last_chapter_number = chapter_number

                # 从跨进程队列获取增量文字（使用异步版本避免阻塞事件循环）
                chunk = await streaming_bus.get_chunk_async(novel_id, timeout=0.05)

                if chunk:
                    event = {
                        "type": "chapter_chunk",
                        "message": "",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "chunk": chunk,
                            "beat_index": getattr(novel, "current_beat_index", 0) or 0,
                        },
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    logger.debug(f"[SSE] 发送 chapter_chunk: {len(chunk)} chars, novel={novel_id}")

                # 心跳
                heartbeat_counter += 1
                if heartbeat_counter >= 20:
                    heartbeat_event = {
                        "type": "heartbeat",
                        "message": "keepalive",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(heartbeat_event, ensure_ascii=False)}\n\n"
                    heartbeat_counter = 0

                # 轮询间隔
                await asyncio.sleep(0.05)

        except Exception as e:
            logger.error(f"Chapter stream error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/{novel_id}/events")
async def autopilot_events(novel_id: str):
    """SSE 实时状态推送（每 3 秒）"""
    novel_repo = get_novel_repository()
    chapter_repo = get_chapter_repository()

    async def event_generator():
        while True:
            try:
                novel = novel_repo.get_by_id(NovelId(novel_id))
                if not novel:
                    break
                chapters = chapter_repo.list_by_novel(NovelId(novel_id))
                total_words = sum(
                    c.word_count.value if hasattr(c.word_count, 'value') else c.word_count
                    for c in chapters if c.word_count
                )
                _st = lambda c: c.status.value if hasattr(c.status, 'value') else c.status
                completed = [c for c in chapters if _st(c) == "completed"]
                in_manuscript = [c for c in chapters if _st(c) in ("draft", "completed")]
                tgt = novel.target_chapters or 1

                data = {
                    "autopilot_status": novel.autopilot_status.value,
                    "current_stage": novel.current_stage.value,
                    "current_act": novel.current_act,
                    "current_beat_index": getattr(novel, "current_beat_index", 0),
                    "completed_chapters": len(completed),
                    "manuscript_chapters": len(in_manuscript),
                    "progress_pct": round(len(completed) / tgt * 100, 1) if tgt else 0,
                    "progress_pct_manuscript": round(len(in_manuscript) / tgt * 100, 1) if tgt else 0,
                    "total_words": total_words,
                    "target_chapters": novel.target_chapters,
                    "needs_review": novel.current_stage.value == "paused_for_review",
                    "consecutive_error_count": getattr(novel, "consecutive_error_count", 0),
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                terminal_states = {"stopped", "error", "completed"}
                if novel.autopilot_status.value in terminal_states and \
                   novel.current_stage.value != "paused_for_review":
                    break

                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"SSE error: {e}")
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/{novel_id}/stream-debug")
async def stream_debug(novel_id: str):
    """调试端点：检查流式队列状态"""
    from application.engine.services.streaming_bus import _get_queue, _stream_queue, _injected_queue
    import multiprocessing as mp
    
    queue = _get_queue()
    current_process = mp.current_process()
    
    # 尝试读取一条消息（非阻塞）
    sample_msg = None
    if queue is not None:
        try:
            sample_msg = queue.get_nowait()
            # 把消息放回去
            queue.put(sample_msg)
        except Exception:
            pass
    
    return {
        "novel_id": novel_id,
        "current_process": current_process.name,
        "is_daemon": current_process.daemon,
        "queue_available": queue is not None,
        "_stream_queue_set": _stream_queue is not None,
        "_injected_queue_set": _injected_queue is not None,
        "sample_message": sample_msg,
    }
