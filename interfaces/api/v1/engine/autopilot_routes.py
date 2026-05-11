"""自动驾驶控制 API（v2：含审阅确认 + SSE 生成流）"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Tuple
from domain.novel.entities.novel import AutopilotStatus, NovelStage
from domain.novel.entities.chapter import ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.word_count import WordCount
from interfaces.api.dependencies import get_novel_repository, get_chapter_repository
from application.paths import get_db_path
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from application.engine.services.autopilot_log_ring import (
    file_end_offset,
    initial_snapshot_offset,
    install_autopilot_log_ring_handler,
    iter_new_for_novel,
    read_incremental_log_file_lines,
    shorten_log_message,
    snapshot_for_novel,
)

logger = logging.getLogger(__name__)


def _chapter_status_str(c) -> str:
    return c.status.value if hasattr(c.status, "value") else c.status


def resolve_autopilot_current_chapter_number(chapters) -> Optional[int]:
    """与 SSE 日志、进度条一致：有内容的 draft 取最大章号；否则取最大 completed+1（预测下一章）。

    注意：幕级规划时会创建空的 draft 记录，需要忽略内容为空的 draft。
    """
    if not chapters:
        return None
    try:
        # 只考虑有实际内容的 draft（字数 > 0）
        def has_content(c) -> bool:
            wc = c.word_count
            if hasattr(wc, 'value'):
                wc = wc.value
            # 也检查 content 长度（兼容 word_count 为空的情况）
            content_len = len(c.content) if hasattr(c, 'content') and c.content else 0
            return (wc or 0) > 0 or content_len > 0

        drafts_with_content = [
            c for c in chapters
            if _chapter_status_str(c) == "draft" and has_content(c)
        ]
        if drafts_with_content:
            return max(int(c.number) for c in drafts_with_content)

        completed = [c for c in chapters if _chapter_status_str(c) == "completed"]
        if completed:
            return max(int(c.number) for c in completed) + 1
    except Exception:
        return None
    return None


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

# ── 使用统一资源管理器管理线程池和缓存 ──
from application.engine.services.resource_manager import (
    ResourceManager, ThreadPoolResource, CacheResource, create_cache
)

# 初始化资源管理器
_rm = ResourceManager()

# SSE 专用线程池（通过资源管理器管理）
_SSE_THREAD_POOL = ThreadPoolResource(
    ThreadPoolExecutor(max_workers=12, thread_name_prefix="sse-io"),
    name="sse-executor"
)
_rm.register(_SSE_THREAD_POOL)

# 共享状态缓存（带 TTL 过期清理）
_SHARED_STATE_CACHE = CacheResource(
    name="shared_state",
    ttl_seconds=1.0,  # 1 秒 TTL
    max_size=1000
)
_rm.register(_SHARED_STATE_CACHE)

# SSE 连接最大存活时间（秒）：超时后自动断开，避免悬空连接累积
_SSE_MAX_LIFETIME_SECONDS = 7200  # 2 小时

# 与 AutopilotDaemon 中单本挂起阈值一致；守护进程内另有全局 CircuitBreaker（独立进程，API 不可见）
PER_NOVEL_FAILURE_THRESHOLD = 3


class _LightChapter:
    """轻量章节代理对象（SSE 流用，不加载 content 字段，减少 DB IO 和内存）"""
    __slots__ = ('id', 'number', 'title', 'status', 'word_count', 'content')

    def __init__(self, id=None, number=0, title="", status=None):
        self.id = id
        self.number = number
        self.title = title
        self.status = status or ChapterStatus.DRAFT
        self.word_count = WordCount(0)
        self.content = None


async def _is_client_disconnected() -> bool:
    """检测 SSE 客户端是否已断开连接。

    通过短暂让出事件循环控制权，让 uvicorn 检测底层 socket 状态。
    如果客户端已断开，后续 yield 会触发 CancelledError 或 ConnectionReset。
    """
    try:
        await asyncio.sleep(0)
    except asyncio.CancelledError:
        return True
    return False


def _stage_name_zh(stage: str) -> str:
    """阶段枚举值 → 中文（与前端驾驶舱一致）"""
    m = {
        "planning": "宏观规划",
        "macro_planning": "宏观规划",
        "act_planning": "幕级规划",
        "writing": "正文撰写",
        "auditing": "章节审计",
        "reviewing": "待审阅确认",
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


def _audit_event_message(event_type: str, data: Dict[str, Any]) -> str:
    """生成审计事件的消息文本"""
    messages = {
        "audit_start": lambda d: f"🔍 开始审计第 {d.get('chapter_number', '?')} 章（{d.get('word_count', 0)} 字）",
        "audit_voice_check": lambda d: f"📊 文风预检中...",
        "audit_voice_result": lambda d: (
            f"📊 文风相似度: {d.get('similarity_score'):.1%}" + (" ⚠️ 偏离告警" if d.get('drift_alert') else "")
            if d.get('similarity_score') is not None
            else "📊 文风相似度: 指纹样本不足（需 ≥10 个采血样本）"
        ),
        "audit_aftermath": lambda d: f"🔄 章后管线处理中...",
        "audit_tension": lambda d: f"⚡ 张力打分中...",
        "audit_tension_result": lambda d: f"⚡ 张力值: {d.get('tension', 'N/A')}/10",
        "audit_complete": lambda d: f"✅ 第 {d.get('chapter_number', '?')} 章审计完成" + (" 🎉全书完成！" if d.get('is_completed') else ""),
    }
    return messages.get(event_type, lambda d: f"审计事件: {event_type}")(data)


def _build_fallback_status(novel) -> Dict[str, Any]:
    """DB 被锁时的降级状态响应：只返回 novels 表中的字段，不含章节统计。

    关键作用：审计期间守护进程持写锁时，/status 仍能返回基本状态，
    前端不会卡死（至少能看到「审计中」和 audit_progress）。
    """
    target = novel.target_chapters or 1
    twpc = getattr(novel, "target_words_per_chapter", None) or 2500
    lacn = getattr(novel, "last_audit_chapter_number", None)
    last_tension = int(getattr(novel, "last_chapter_tension", 0) or 0)
    last_chapter_audit = None
    if lacn is not None:
        last_chapter_audit = {
            "chapter_number": int(lacn),
            "tension": last_tension,
            "drift_alert": bool(getattr(novel, "last_audit_drift_alert", False)),
            "similarity_score": getattr(novel, "last_audit_similarity", None),
            "narrative_sync_ok": bool(getattr(novel, "last_audit_narrative_ok", True)),
            "at": getattr(novel, "last_audit_at", None),
            "vector_stored": bool(getattr(novel, "last_audit_vector_stored", False)),
            "foreshadow_stored": bool(getattr(novel, "last_audit_foreshadow_stored", False)),
            "triples_extracted": bool(getattr(novel, "last_audit_triples_extracted", False)),
            "quality_scores": getattr(novel, "last_audit_quality_scores", {}) or {},
            "issues": getattr(novel, "last_audit_issues", []) or [],
        }
    return {
        "autopilot_status": novel.autopilot_status.value if hasattr(novel.autopilot_status, "value") else novel.autopilot_status,
        "current_stage": novel.current_stage.value if hasattr(novel.current_stage, "value") else novel.current_stage,
        "current_act": getattr(novel, "current_act", 0),
        "current_chapter_in_act": getattr(novel, "current_chapter_in_act", 0),
        "current_beat_index": getattr(novel, "current_beat_index", 0),
        "current_auto_chapters": getattr(novel, "current_auto_chapters", 0),
        "max_auto_chapters": getattr(novel, "max_auto_chapters", 9999),
        "target_chapters": novel.target_chapters,
        "target_words_per_chapter": twpc,
        "target_plan_total_words": target * twpc,
        "last_chapter_tension": last_tension,
        "consecutive_error_count": getattr(novel, "consecutive_error_count", 0),
        "total_words": 0,  # 降级：无法统计
        "completed_chapters": 0,  # 降级
        "progress_pct": 0.0,  # 降级
        "manuscript_chapters": 0,  # 降级
        "progress_pct_manuscript": 0.0,  # 降级
        "current_chapter_number": None,
        "needs_review": (novel.current_stage.value if hasattr(novel.current_stage, "value") else novel.current_stage) == "paused_for_review",
        "auto_approve_mode": getattr(novel, "auto_approve_mode", False),
        "last_chapter_audit": last_chapter_audit,
        "audit_progress": getattr(novel, "audit_progress", None),
        "_degraded": True,  # 前端可据此显示「数据同步中」提示
    }


# ── SSE / 高频接口：同步仓储与文件 IO 放入线程池，避免阻塞 asyncio 事件循环（否则会拖死全站 API）──


def _get_shared_state_for_novel(novel_id: str) -> Optional[Dict[str, Any]]:
    """从跨进程共享内存读取小说实时状态（零 DB IO，纳秒级响应）。

    架构原则：状态走内存，数据走磁盘。守护进程写入共享字典，API 进程直接读取。
    """
    try:
        from interfaces.main import get_shared_novel_state
        return get_shared_novel_state(novel_id)
    except Exception:
        return None


def _build_autopilot_status_sync(novel_id: str) -> Optional[Dict[str, Any]]:
    """get_autopilot_status 的同步实现（供 asyncio.to_thread 调用）。

    共享内存提供阶段、审计进度、张力等；完稿/书稿/总字数以短超时 SQLite 聚合为准
   （_build_status_with_shared），再与共享字段合并。DB 被锁或异常时降级为纯共享内存
    或占位响应。

    修复：曾经 _cached_completed_chapters=0 因 `is not None` 走纯内存导致永久 0/0/总字数 0。
    """
    # ── 第一层：共享内存（阶段）+ DB 校准（章节聚合）──
    shared = _get_shared_state_for_novel(novel_id)
    if shared and shared.get("_updated_at"):
        # 共享状态存在且有效（30 秒内更新过）
        age = time.time() - shared["_updated_at"]
        if age < 60.0:  # 🔥 放宽到60秒，避免LLM调用期间误判过期
            logger.debug("status 共享内存+DB 校准 novel=%s age=%.1fs", novel_id, age)
            return _build_status_with_shared(novel_id, shared)

    # ── 第二层：经 DatabaseConnection 只读（与消费者共用 WAL 通道）──
    import sqlite3
    from application.paths import get_db_path
    from infrastructure.persistence.database.connection import get_database

    novel: Any = None

    try:
        db = get_database(get_db_path())

        row = db.fetch_one(
            "SELECT * FROM novels WHERE id = ?",
            (novel_id,),
        )
        if not row:
            return None
        novel = dict(row)

        agg_rows = db.fetch_all(
            "SELECT status, SUM(LENGTH(COALESCE(content,''))) as total_wc FROM chapters WHERE novel_id = ? GROUP BY status",
            (novel_id,),
        )
        completed_count = 0
        in_manuscript_count = 0
        total_words = 0
        for r in agg_rows:
            s = r["status"] or ""
            wc = r["total_wc"] or 0
            total_words += wc
            if s == "completed":
                completed_count += 1
                in_manuscript_count += 1
            elif s == "draft":
                in_manuscript_count += 1

        draft_row = db.fetch_one(
            "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'draft' AND COALESCE(LENGTH(content),0) > 0",
            (novel_id,),
        )
        if draft_row and draft_row["max_num"]:
            current_chapter_number = draft_row["max_num"]
        else:
            completed_max = db.fetch_one(
                "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'completed'",
                (novel_id,),
            )
            current_chapter_number = (
                (completed_max["max_num"] + 1)
                if (completed_max and completed_max["max_num"])
                else None
            )

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower() or "busy" in str(e).lower():
            logger.debug("status DB 被锁，降级到共享内存 novel=%s", novel_id)
            # 🔥 关键修复：DB 被锁时不再查 DB（novel_repo.get_by_id 也会被锁住！），
            # 改用共享内存构建降级状态。这是之前线程池耗尽的直接原因之一：
            # DB 锁 → 降级查 novel_repo → 也被锁 → 线程池线程被占满 → 所有 API 卡死
            if shared and shared.get("_updated_at"):
                return _build_status_pure_memory(novel_id, shared)
            return _build_fallback_from_shared(novel_id, shared)
        raise
    except Exception:
        # 🔥 同上：任何 DB 异常都优先用共享内存，不再查 DB
        logger.debug("status DB 异常，降级到共享内存 novel=%s", novel_id)
        if shared and shared.get("_updated_at"):
            return _build_status_pure_memory(novel_id, shared)
        return _build_fallback_from_shared(novel_id, shared)

    # 合并共享内存中的实时状态（如果存在）
    if shared:
        novel["current_stage"] = shared.get("current_stage", novel.get("current_stage"))
        novel["audit_progress"] = shared.get("audit_progress", novel.get("audit_progress"))
        novel["last_chapter_tension"] = shared.get("last_chapter_tension", novel.get("last_chapter_tension"))
        novel["last_audit_similarity"] = shared.get("last_audit_similarity", novel.get("last_audit_similarity"))
        novel["last_audit_drift_alert"] = shared.get("last_audit_drift_alert", novel.get("last_audit_drift_alert"))

    target = (novel.get("target_chapters") if isinstance(novel, dict) else novel.target_chapters) or 1
    twpc = (novel.get("target_words_per_chapter") if isinstance(novel, dict) else getattr(novel, "target_words_per_chapter", None)) or 2500

    lacn = novel.get("last_audit_chapter_number") if isinstance(novel, dict) else getattr(novel, "last_audit_chapter_number", None)
    last_tension = int((novel.get("last_chapter_tension") if isinstance(novel, dict) else getattr(novel, "last_chapter_tension", 0)) or 0)
    last_chapter_audit = None
    if lacn is not None:
        last_chapter_audit = {
            "chapter_number": int(lacn),
            "tension": last_tension,
            "drift_alert": bool((novel.get("last_audit_drift_alert") if isinstance(novel, dict) else getattr(novel, "last_audit_drift_alert", False))),
            "similarity_score": novel.get("last_audit_similarity") if isinstance(novel, dict) else getattr(novel, "last_audit_similarity", None),
            "narrative_sync_ok": bool((novel.get("last_audit_narrative_ok") if isinstance(novel, dict) else getattr(novel, "last_audit_narrative_ok", True))),
            "at": novel.get("last_audit_at") if isinstance(novel, dict) else getattr(novel, "last_audit_at", None),
            "vector_stored": bool((novel.get("last_audit_vector_stored") if isinstance(novel, dict) else getattr(novel, "last_audit_vector_stored", False))),
            "foreshadow_stored": bool((novel.get("last_audit_foreshadow_stored") if isinstance(novel, dict) else getattr(novel, "last_audit_foreshadow_stored", False))),
            "triples_extracted": bool((novel.get("last_audit_triples_extracted") if isinstance(novel, dict) else getattr(novel, "last_audit_triples_extracted", False))),
            "quality_scores": (novel.get("last_audit_quality_scores") if isinstance(novel, dict) else getattr(novel, "last_audit_quality_scores", {})) or {},
            "issues": (novel.get("last_audit_issues") if isinstance(novel, dict) else getattr(novel, "last_audit_issues", [])) or [],
        }

    _ap_status = novel.get("autopilot_status") if isinstance(novel, dict) else novel.autopilot_status
    _ap_status_str = _ap_status if isinstance(_ap_status, str) else (_ap_status.value if hasattr(_ap_status, "value") else str(_ap_status))
    _stage = novel.get("current_stage") if isinstance(novel, dict) else novel.current_stage
    _stage_str = _stage if isinstance(_stage, str) else (_stage.value if hasattr(_stage, "value") else str(_stage))

    # 🔥 读取守护进程心跳（判断后端是否存活）
    daemon_heartbeat = None
    daemon_alive = False
    try:
        from interfaces.main import _get_shared_state
        g_state = _get_shared_state()
        daemon_heartbeat = g_state.get("_daemon_heartbeat")
        if daemon_heartbeat:
            daemon_alive = (time.time() - daemon_heartbeat) < 60.0  # 60 秒内有心跳视为存活
    except Exception:
        pass

    return {
        "autopilot_status": _ap_status_str,
        "current_stage": _stage_str,
        "current_act": novel.get("current_act") if isinstance(novel, dict) else novel.current_act,
        "current_chapter_in_act": novel.get("current_chapter_in_act") if isinstance(novel, dict) else novel.current_chapter_in_act,
        "current_beat_index": novel.get("current_beat_index") if isinstance(novel, dict) else getattr(novel, "current_beat_index", 0),
        "current_auto_chapters": novel.get("current_auto_chapters") if isinstance(novel, dict) else getattr(novel, "current_auto_chapters", 0),
        "max_auto_chapters": novel.get("max_auto_chapters") if isinstance(novel, dict) else getattr(novel, "max_auto_chapters", 9999),
        "target_chapters": novel.get("target_chapters") if isinstance(novel, dict) else novel.target_chapters,
        "target_words_per_chapter": twpc,
        "target_plan_total_words": target * twpc,
        "last_chapter_tension": last_tension,
        "consecutive_error_count": novel.get("consecutive_error_count") if isinstance(novel, dict) else getattr(novel, "consecutive_error_count", 0),
        "total_words": total_words,
        "completed_chapters": completed_count,
        "progress_pct": round(completed_count / target * 100, 1) if target else 0,
        "manuscript_chapters": in_manuscript_count,
        "progress_pct_manuscript": round(in_manuscript_count / target * 100, 1) if target else 0,
        "current_chapter_number": current_chapter_number,
        "needs_review": _stage_str == "paused_for_review",
        "auto_approve_mode": novel.get("auto_approve_mode") if isinstance(novel, dict) else getattr(novel, "auto_approve_mode", False),
        "last_chapter_audit": last_chapter_audit,
        "audit_progress": novel.get("audit_progress") if isinstance(novel, dict) else getattr(novel, "audit_progress", None),
        "daemon_alive": daemon_alive,
        "daemon_heartbeat_at": daemon_heartbeat,
    }


def _build_fallback_from_shared(novel_id: str, shared: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """🔥 DB 不可用且共享内存数据不全时的兜底状态。

    与 _build_fallback_status 不同：此方法不查 DB，完全基于共享内存。
    即使共享内存数据不全，也返回一个基本可用的状态，前端不会卡死。
    """
    if not shared:
        # 完全没有共享内存数据：返回最小状态
        return {
            "autopilot_status": "running",
            "current_stage": "syncing",
            "current_act": None,
            "current_chapter_in_act": None,
            "current_beat_index": 0,
            "current_auto_chapters": 0,
            "max_auto_chapters": 9999,
            "target_chapters": 0,
            "target_words_per_chapter": 2500,
            "target_plan_total_words": 0,
            "last_chapter_tension": 0,
            "consecutive_error_count": 0,
            "total_words": 0,
            "completed_chapters": 0,
            "progress_pct": 0,
            "manuscript_chapters": 0,
            "progress_pct_manuscript": 0,
            "current_chapter_number": None,
            "needs_review": False,
            "auto_approve_mode": False,
            "last_chapter_audit": None,
            "audit_progress": None,
            "_degraded": True,
            "_message": "数据同步中，请稍候...",
        }

    # 有共享内存但可能不完整
    return _build_status_pure_memory(novel_id, shared)


def _build_status_pure_memory(novel_id: str, shared: Dict[str, Any]) -> Dict[str, Any]:
    """🔥 纯共享内存路径：完全跳过 DB，1ms 返回。

    这是最关键的架构优化：当守护进程在写作/审计期间持有 DB 写锁时，
    /status 请求完全不碰 DB，只读共享内存，实现"状态与数据分离"。

    前提：守护进程在每次更新共享状态时缓存了统计信息（_cached_* 字段）。
    """
    # 读取守护进程心跳
    daemon_heartbeat = None
    daemon_alive = False
    try:
        from interfaces.main import _get_shared_state
        g_state = _get_shared_state()
        daemon_heartbeat = g_state.get("_daemon_heartbeat")
        if daemon_heartbeat:
            daemon_alive = (time.time() - daemon_heartbeat) < 60.0
    except Exception:
        pass

    # 构建 last_chapter_audit
    lacn = shared.get("last_audit_chapter_number")
    last_tension = int(shared.get("last_chapter_tension", 0) or 0)
    last_chapter_audit = None
    if lacn is not None:
        last_chapter_audit = {
            "chapter_number": int(lacn),
            "tension": last_tension,
            "drift_alert": bool(shared.get("last_audit_drift_alert", False)),
            "similarity_score": shared.get("last_audit_similarity"),
            "narrative_sync_ok": bool(shared.get("last_audit_narrative_ok", True)),
            "at": shared.get("last_audit_at"),
            "vector_stored": bool(shared.get("last_audit_vector_stored", False)),
            "foreshadow_stored": bool(shared.get("last_audit_foreshadow_stored", False)),
            "triples_extracted": bool(shared.get("last_audit_triples_extracted", False)),
            "quality_scores": shared.get("last_audit_quality_scores", {}) or {},
            "issues": shared.get("last_audit_issues", []) or [],
        }

    completed_count = shared.get("_cached_completed_chapters", 0)
    manuscript_count = shared.get("_cached_manuscript_chapters", 0)
    total_words = shared.get("_cached_total_words", 0)
    target = shared.get("target_chapters", 1) or 1
    twpc = shared.get("target_words_per_chapter", 2500) or 2500
    stage = shared.get("current_stage", "writing")

    return {
        "autopilot_status": shared.get("autopilot_status", "running"),
        "current_stage": stage,
        "current_act": shared.get("current_act"),
        "current_act_title": shared.get("current_act_title"),
        "current_act_description": shared.get("current_act_description"),
        "current_chapter_in_act": shared.get("current_chapter_in_act"),
        "current_beat_index": shared.get("current_beat_index", 0),
        "current_auto_chapters": shared.get("current_auto_chapters", 0),
        "max_auto_chapters": shared.get("max_auto_chapters", 9999),
        "target_chapters": target,
        "target_words_per_chapter": twpc,
        "target_plan_total_words": target * twpc,
        "last_chapter_tension": last_tension,
        "consecutive_error_count": shared.get("consecutive_error_count", 0),
        "total_words": total_words,
        "completed_chapters": completed_count,
        "progress_pct": round(completed_count / target * 100, 1) if target else 0,
        "manuscript_chapters": manuscript_count,
        "progress_pct_manuscript": round(manuscript_count / target * 100, 1) if target else 0,
        "current_chapter_number": shared.get("_cached_current_chapter_number"),
        "needs_review": stage == "paused_for_review",
        "auto_approve_mode": shared.get("auto_approve_mode", False),
        "last_chapter_audit": last_chapter_audit,
        "audit_progress": shared.get("audit_progress"),
        "_from_shared_memory": True,
        "daemon_alive": daemon_alive,
        "daemon_heartbeat_at": daemon_heartbeat,
        "writing_substep": shared.get("writing_substep", ""),
        "writing_substep_label": shared.get("writing_substep_label", ""),
        "total_beats": shared.get("total_beats", 0),
        "beat_focus": shared.get("beat_focus", ""),
        "beat_target_words": shared.get("beat_target_words", 0),
        "accumulated_words": shared.get("accumulated_words", 0),
        "chapter_target_words": shared.get("chapter_target_words", 0),
        "context_tokens": shared.get("context_tokens", 0),
        "beat_hard_cap": shared.get("beat_hard_cap", 0),
        "beat_phase": shared.get("beat_phase", ""),
        "beat_max_words_hint": shared.get("beat_max_words_hint", 0),
        "beat_remaining_budget": shared.get("beat_remaining_budget", 0),
        "last_smart_truncate": shared.get("last_smart_truncate"),
    }


def _build_status_with_shared(novel_id: str, shared: Dict[str, Any]) -> Dict[str, Any]:
    """合并共享内存（阶段、审计进度等）与 SQLite 章节聚合（完稿/书稿/总字数）。

    聚合经 `get_database` 只读路径；失败时用共享内存 _cached_* 与 novels 行字段兜底，
    避免在守护进程持锁时长阻塞 /status。
    """
    from application.paths import get_db_path
    from infrastructure.persistence.database.connection import get_database

    db_path = get_db_path()
    completed_count = 0
    in_manuscript_count = 0
    total_words = 0
    current_chapter_number = None
    target = 1
    twpc = 2500

    try:
        db = get_database(db_path)

        agg_rows = db.fetch_all(
            "SELECT status, SUM(LENGTH(COALESCE(content,''))) as total_wc FROM chapters WHERE novel_id = ? GROUP BY status",
            (novel_id,),
        )
        for r in agg_rows:
            s = r["status"] or ""
            wc = r["total_wc"] or 0
            total_words += wc
            if s == "completed":
                completed_count += 1
                in_manuscript_count += 1
            elif s == "draft":
                in_manuscript_count += 1

        draft_row = db.fetch_one(
            "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'draft' AND COALESCE(LENGTH(content),0) > 0",
            (novel_id,),
        )
        if draft_row and draft_row["max_num"]:
            current_chapter_number = draft_row["max_num"]
        else:
            completed_max = db.fetch_one(
                "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'completed'",
                (novel_id,),
            )
            current_chapter_number = (
                (completed_max["max_num"] + 1)
                if (completed_max and completed_max["max_num"])
                else None
            )

        row = db.fetch_one(
            "SELECT target_chapters, target_words_per_chapter, autopilot_status, auto_approve_mode, consecutive_error_count FROM novels WHERE id = ?",
            (novel_id,),
        )
        if row:
            target = row["target_chapters"] or 1
            twpc = row["target_words_per_chapter"] or 2500
            autopilot_status = row["autopilot_status"] or "stopped"
            auto_approve_mode = bool(row["auto_approve_mode"])
            consecutive_error_count = row["consecutive_error_count"] or 0
        else:
            autopilot_status = "stopped"
            auto_approve_mode = False
            consecutive_error_count = 0

    except Exception as e:
        logger.debug("共享内存模式 DB 统计查询失败 novel=%s: %s，使用共享内存缓存值", novel_id, e)
        # 🔥 关键修复：DB 查询失败时，从共享内存读取缓存值，而不是返回 0
        # 守护进程每次更新共享状态时会写入缓存统计
        autopilot_status = shared.get("autopilot_status", "running")
        auto_approve_mode = shared.get("auto_approve_mode", False)
        consecutive_error_count = shared.get("consecutive_error_count", 0)
        target = shared.get("target_chapters", 1) or 1
        twpc = shared.get("target_words_per_chapter", 2500) or 2500
        completed_count = shared.get("_cached_completed_chapters", 0)
        in_manuscript_count = shared.get("_cached_manuscript_chapters", 0)
        total_words = shared.get("_cached_total_words", 0)
        current_chapter_number = shared.get("_cached_current_chapter_number")

    # 构建 last_chapter_audit
    lacn = shared.get("last_audit_chapter_number")
    last_tension = int(shared.get("last_chapter_tension", 0) or 0)
    last_chapter_audit = None
    if lacn is not None:
        last_chapter_audit = {
            "chapter_number": int(lacn),
            "tension": last_tension,
            "drift_alert": bool(shared.get("last_audit_drift_alert", False)),
            "similarity_score": shared.get("last_audit_similarity"),
            "narrative_sync_ok": bool(shared.get("last_audit_narrative_ok", True)),
            "at": shared.get("last_audit_at"),
            "vector_stored": bool(shared.get("last_audit_vector_stored", False)),
            "foreshadow_stored": bool(shared.get("last_audit_foreshadow_stored", False)),
            "triples_extracted": bool(shared.get("last_audit_triples_extracted", False)),
            "quality_scores": shared.get("last_audit_quality_scores", {}) or {},
            "issues": shared.get("last_audit_issues", []) or [],
        }

    stage = shared.get("current_stage", "writing")

    # 🔥 读取守护进程心跳
    daemon_heartbeat = None
    daemon_alive = False
    try:
        from interfaces.main import _get_shared_state
        g_state = _get_shared_state()
        daemon_heartbeat = g_state.get("_daemon_heartbeat")
        if daemon_heartbeat:
            daemon_alive = (time.time() - daemon_heartbeat) < 60.0
    except Exception:
        pass

    return {
        "autopilot_status": autopilot_status,
        "current_stage": stage,
        "current_act": shared.get("current_act"),
        "current_act_title": shared.get("current_act_title"),
        "current_act_description": shared.get("current_act_description"),
        "current_chapter_in_act": shared.get("current_chapter_in_act"),
        "current_beat_index": shared.get("current_beat_index", 0),
        "current_auto_chapters": shared.get("current_auto_chapters", 0),
        "max_auto_chapters": shared.get("max_auto_chapters", 9999),
        "target_chapters": target,
        "target_words_per_chapter": twpc,
        "target_plan_total_words": target * twpc,
        "last_chapter_tension": last_tension,
        "consecutive_error_count": consecutive_error_count,
        "total_words": total_words,
        "completed_chapters": completed_count,
        "progress_pct": round(completed_count / target * 100, 1) if target else 0,
        "manuscript_chapters": in_manuscript_count,
        "progress_pct_manuscript": round(in_manuscript_count / target * 100, 1) if target else 0,
        "current_chapter_number": current_chapter_number,
        "needs_review": stage == "paused_for_review",
        "auto_approve_mode": auto_approve_mode,
        "last_chapter_audit": last_chapter_audit,
        "audit_progress": shared.get("audit_progress"),
        "_from_shared_memory": True,  # 前端可据此显示「实时同步中」提示
        "daemon_alive": daemon_alive,
        "daemon_heartbeat_at": daemon_heartbeat,
        # ★ V9 细化字段
        "writing_substep": shared.get("writing_substep", ""),
        "writing_substep_label": shared.get("writing_substep_label", ""),
        "total_beats": shared.get("total_beats", 0),
        "beat_focus": shared.get("beat_focus", ""),
        "beat_target_words": shared.get("beat_target_words", 0),
        "accumulated_words": shared.get("accumulated_words", 0),
        "chapter_target_words": shared.get("chapter_target_words", 0),
        "context_tokens": shared.get("context_tokens", 0),
        "beat_hard_cap": shared.get("beat_hard_cap", 0),
        "beat_phase": shared.get("beat_phase", ""),
        "beat_max_words_hint": shared.get("beat_max_words_hint", 0),
        "beat_remaining_budget": shared.get("beat_remaining_budget", 0),
        "last_smart_truncate": shared.get("last_smart_truncate"),
    }


def _chapter_stream_poll_sync(novel_repo, chapter_repo, novel_id: str):
    """章节 SSE：单轮 DB 读（写作阶段才拉全章节列表）。

    🔥 关键优化：写作阶段也改用轻量 SQL 聚合查询，不再全量加载章节对象。
    chapter_repo.list_by_novel 会加载所有章节的 content 字段（可能数百KB），
    审计期间 DB 被守护进程写锁持有时会阻塞线程池 5 秒以上。
    前端只需要知道当前章节号和状态，不需要全部章节对象。
    """
    novel = novel_repo.get_by_id(NovelId(novel_id))
    if not novel:
        return None, None
    chapters = None
    if novel.current_stage.value == "writing":
        # 🔥 轻量查询：只获取 draft 章节的编号和基本信息，不加载 content
        try:
            db = chapter_repo.db if hasattr(chapter_repo, 'db') else None
            if db is not None:
                rows = db.fetch_all(
                    "SELECT id, number, title, status FROM chapters WHERE novel_id = ? AND status = 'draft' ORDER BY number",
                    (novel_id,)
                )
                if rows:
                    chapters = []
                    for r in rows:
                        lc = _LightChapter(
                            id=r['id'],
                            number=r['number'],
                            title=r['title'],
                            status=ChapterStatus(r['status']) if r['status'] else ChapterStatus.DRAFT,
                        )
                        chapters.append(lc)
        except Exception:
            # DB 被锁时跳过，前端通过 /status 获取进度
            pass
    return novel, chapters


def _chapter_stream_chunks_sync(novel_id: str, max_chunks: int) -> List[str]:
    from application.engine.services.streaming_bus import streaming_bus

    return streaming_bus.get_chunks_batch(novel_id, max_chunks=max_chunks)


def _chapter_stream_tick_sync(novel_repo, chapter_repo, novel_id: str, max_chunks: int):
    """单次轮询：DB 读取 + chunks 获取合并在同一线程池任务中，减少 asyncio.to_thread 调用次数。"""
    novel, chapters = _chapter_stream_poll_sync(novel_repo, chapter_repo, novel_id)
    chunks = _chapter_stream_chunks_sync(novel_id, max_chunks) if novel else []
    return novel, chapters, chunks


def _autopilot_events_tick_sync(novel_repo, chapter_repo, novel_id: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """返回 (payload, 本轮 yield 后是否应结束流)；novel 不存在时 (None, True)。

    若共享里章节缓存非全零则走内存快路径；否则用与 /status 一致的 SQLite 聚合。
    """
    # 读共享快照（可能仅含阶段信息；计数见下方分支）
    shared = _get_shared_state_for_novel_cached(novel_id)

    if shared and shared.get("_updated_at") and shared.get("_cached_completed_chapters") is not None:
        cc = int(shared.get("_cached_completed_chapters") or 0)
        mw = shared.get("_cached_manuscript_chapters")
        mw_i = int(mw) if mw is not None else 0
        tw = shared.get("_cached_total_words")
        tw_i = int(tw) if tw is not None else 0
        # 与 /status 一致：三连 0 的快路径不可靠（历史上常为占位），改走 DB 聚合
        cache_looks_populated = cc > 0 or mw_i > 0 or tw_i > 0
        if cache_looks_populated:
            tgt = shared.get("target_chapters", 1) or 1
            data = {
                "autopilot_status": shared.get("autopilot_status", "stopped"),
                "current_stage": shared.get("current_stage", "writing"),
                "current_act": shared.get("current_act"),
                "current_act_title": shared.get("current_act_title"),
                "current_act_description": shared.get("current_act_description"),
                "current_beat_index": shared.get("current_beat_index", 0) or 0,
                "current_auto_chapters": shared.get("current_auto_chapters", 0) or 0,
                "target_chapters": tgt,
                "progress_pct": round((shared.get("_cached_completed_chapters", 0) or 0) / tgt * 100, 1) if tgt else 0,
                "total_words": shared.get("_cached_total_words", 0) or 0,
                "completed_chapters": shared.get("_cached_completed_chapters", 0) or 0,
                "current_chapter_number": shared.get("_cached_current_chapter_number"),
                "audit_progress": shared.get("audit_progress"),
                "last_chapter_tension": shared.get("last_chapter_tension", 0) or 0,
            }
            terminal_states = {"stopped", "error", "completed"}
            should_break = data["autopilot_status"] in terminal_states
            return data, should_break

    # 慢路径：novel + SQLite 聚合（共享无可用缓存或缓存不可信时）
    novel = novel_repo.get_by_id(NovelId(novel_id))
    if not novel:
        return None, True

    # 轻量 SQL 聚合
    try:
        db = chapter_repo.db if hasattr(chapter_repo, 'db') else None
        if db is not None:
            agg_rows = db.fetch_all(
                "SELECT status, SUM(LENGTH(COALESCE(content,''))) as total_wc FROM chapters WHERE novel_id = ? GROUP BY status",
                (novel_id,)
            )
            ev_completed = 0
            ev_in_manuscript = 0
            ev_total_words = 0
            for row in agg_rows:
                s = row['status'] or ''
                wc = row['total_wc'] or 0
                ev_total_words += wc
                if s == 'completed':
                    ev_completed += 1
                    ev_in_manuscript += 1
                elif s == 'draft':
                    ev_in_manuscript += 1

            draft_row = db.fetch_one(
                "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'draft' AND COALESCE(LENGTH(content),0) > 0",
                (novel_id,)
            )
            if draft_row and draft_row['max_num']:
                ev_chapter_number = draft_row['max_num']
            else:
                completed_max = db.fetch_one(
                    "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'completed'",
                    (novel_id,)
                )
                ev_chapter_number = (completed_max['max_num'] + 1) if (completed_max and completed_max['max_num']) else None
        else:
            raise RuntimeError("no db handle")
    except Exception:
        # DB 查询失败时用共享内存降级
        shared_ev = _get_shared_state_for_novel_cached(novel_id)
        ev_total_words = int(shared_ev.get("_cached_total_words", 0)) if shared_ev else 0
        ev_completed = shared_ev.get("_cached_completed_chapters", 0) if shared_ev else 0
        ev_in_manuscript = shared_ev.get("_cached_manuscript_chapters", 0) if shared_ev else 0
        ev_chapter_number = shared_ev.get("_cached_current_chapter_number") if shared_ev else None

    tgt = novel.target_chapters or 1
    data = {
        "autopilot_status": novel.autopilot_status.value,
        "current_stage": novel.current_stage.value,
        "current_act": novel.current_act,
        "current_act_title": getattr(novel, "current_act_title", None) or getattr(novel, "_current_act_title", None),
        "current_act_description": getattr(novel, "current_act_description", None) or getattr(novel, "_current_act_description", None),
        "current_beat_index": getattr(novel, "current_beat_index", 0),
        "current_chapter_number": ev_chapter_number,
        "completed_chapters": ev_completed,
        "manuscript_chapters": ev_in_manuscript,
        "progress_pct": round(ev_completed / tgt * 100, 1) if tgt else 0,
        "progress_pct_manuscript": round(ev_in_manuscript / tgt * 100, 1) if tgt else 0,
        "total_words": ev_total_words,
        "target_chapters": novel.target_chapters,
        "needs_review": novel.current_stage.value == "paused_for_review",
        "consecutive_error_count": getattr(novel, "consecutive_error_count", 0),
    }
    terminal_states = {"stopped", "error", "completed"}
    should_break = (
        novel.autopilot_status.value in terminal_states
        and novel.current_stage.value != "paused_for_review"
    )
    return data, should_break


def _log_stream_replay_sync(novel_id: str, after_seq: int, last_seq_cursor: int) -> Tuple[List[str], int]:
    """历史快照重放：返回待 yield 的完整 SSE 行与更新后的 last_seq_cursor。"""
    out: List[str] = []
    last = last_seq_cursor
    if after_seq == 0:
        for snap in snapshot_for_novel(novel_id, limit=400):
            ev = {
                "type": "log_line",
                "message": shorten_log_message(snap.message),
                "timestamp": snap.timestamp_iso,
                "metadata": {
                    "seq": snap.seq,
                    "level": snap.level,
                    "logger": snap.logger_name,
                    "replay": True,
                },
            }
            out.append(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n")
            last = max(last, snap.seq)
    return out, last


# ── 共享内存读取缓存（使用资源管理器的 CacheResource）──
# 缓存逻辑已移至 _SHARED_STATE_CACHE，以下函数为便捷封装


def _get_shared_state_for_novel_cached(novel_id: str) -> Optional[Dict[str, Any]]:
    """带缓存的共享内存读取（1 秒 TTL），减少 Manager.dict 代理 IPC 开销。

    multiprocessing.Manager.dict() 的每次 .get() 都是一次跨进程 IPC 调用（~0.1-1ms），
    SSE 每 2 秒轮询一次 + /status 每 3-5 秒轮询一次，积少成多。
    加 1 秒本地缓存后，同一秒内的多次读取只做一次 IPC。
    """
    # 使用资源管理器的缓存
    cached = _SHARED_STATE_CACHE.get(novel_id)
    if cached is not None:
        return cached

    # 缓存过期或不存在，从共享内存读取
    data = _get_shared_state_for_novel(novel_id)
    if data is not None:
        _SHARED_STATE_CACHE.set(novel_id, data)
    return data


def _log_stream_io_tick_sync(
    novel_repo,
    chapter_repo,
    novel_id: str,
    log_file_path: str,
    file_cursor: int,
    last_seq_cursor: int,
):
    """日志 SSE 单轮：读库 + tail 日志文件 + 内存环。novel 不存在时 novel 为 None。

    🔥 架构优化：优先从共享内存读取，避免 DB 锁竞争。
    """
    # 🔥 优先从共享内存读取状态（零 DB IO）
    shared = _get_shared_state_for_novel_cached(novel_id)

    # 构造一个轻量 novel 代理对象
    class _LightNovel:
        def __init__(self, shared_data):
            self._shared = shared_data or {}
            self.current_stage = type('obj', (object,), {'value': self._shared.get('current_stage', 'writing')})()
            self.autopilot_status = type('obj', (object,), {'value': self._shared.get('autopilot_status', 'stopped')})()
            # 🔥 添加缺失的属性
            self.current_act = self._shared.get('current_act')
            self.current_chapter_in_act = self._shared.get('current_chapter_in_act')
            self.current_beat_index = self._shared.get('current_beat_index', 0)
            self.target_chapters = self._shared.get('target_chapters', 0)
            self.title = self._shared.get('title', '')

    novel = _LightNovel(shared)

    # 🔥 只在共享内存没有数据时才查 DB（降级路径）
    if not shared or not shared.get("_updated_at"):
        db_novel = novel_repo.get_by_id(NovelId(novel_id))
        if not db_novel:
            return None, None, None, file_cursor, []
        novel = db_novel

    # 🔥 写作阶段：始终从数据库查询实时统计（缓存只在章节完成时更新）
    chapters_stats = None
    if novel.current_stage.value == "writing":
        try:
            db = chapter_repo.db if hasattr(chapter_repo, 'db') else None
            if db is not None:
                # 获取当前章节号
                draft_row = db.fetch_one(
                    "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'draft' AND COALESCE(LENGTH(content),0) > 0",
                    (novel_id,)
                )
                current_ch = None
                if draft_row and draft_row['max_num']:
                    current_ch = draft_row['max_num']
                # 聚合统计
                agg_rows = db.fetch_all(
                    "SELECT status, SUM(LENGTH(COALESCE(content,''))) as total_wc FROM chapters WHERE novel_id = ? GROUP BY status",
                    (novel_id,)
                )
                completed_cnt = 0
                total_wc = 0
                for r in agg_rows:
                    s = r['status'] or ''
                    wc = r['total_wc'] or 0
                    total_wc += wc
                    if s == 'completed':
                        completed_cnt += 1
                chapters_stats = {
                    'current_chapter_number': current_ch,
                    'completed_count': completed_cnt,
                    'total_words': total_wc,
                }
        except Exception:
            # DB 被锁时使用共享内存缓存
            if shared:
                chapters_stats = {
                    'current_chapter_number': shared.get("_cached_current_chapter_number"),
                    'completed_count': shared.get("_cached_completed_chapters", 0),
                    'total_words': shared.get("_cached_total_words", 0),
                }

    file_lines, new_cursor = read_incremental_log_file_lines(log_file_path, novel_id, file_cursor)
    ring_batch = list(iter_new_for_novel(novel_id, last_seq_cursor, limit=200))

    # 🔥 获取审计事件
    from application.engine.services.streaming_bus import streaming_bus
    stream_data = streaming_bus.get_chunks_and_events_batch(novel_id, max_chunks=200)
    audit_events = stream_data.get("audit_events", [])

    return novel, chapters_stats, file_lines, new_cursor, ring_batch, audit_events


def _log_stream_boot_meta_sync(novel_repo, novel_id: str) -> Dict[str, Any]:
    novel_boot = novel_repo.get_by_id(NovelId(novel_id))
    init_meta: Dict[str, Any] = {}
    if novel_boot:
        init_meta = {
            "stage": novel_boot.current_stage.value,
            "stage_label": _stage_name_zh(novel_boot.current_stage.value),
            "autopilot_status": novel_boot.autopilot_status.value,
            "autopilot_status_label": _autopilot_status_zh(novel_boot.autopilot_status.value),
        }
    return init_meta


def _log_stream_file_cursor_init_sync(log_file_path: str, after_seq: int) -> int:
    if after_seq == 0:
        return initial_snapshot_offset(log_file_path)
    return file_end_offset(log_file_path)


class StartRequest(BaseModel):
    max_auto_chapters: Optional[int] = 9999  # 保护上限，默认几乎无限制，由 target_chapters 控制实际完成点


@router.post("/{novel_id}/start")
async def start_autopilot(novel_id: str, body: StartRequest = StartRequest()):
    """启动自动驾驶（非阻塞版：共享内存先行，DB 持久化异步）

    架构优化：
    1. 先写共享内存（前端立即可见状态变更）
    2. 再异步持久化到 DB（不阻塞事件循环，守护进程 DB 被锁时不卡 API）
    3. 最后发布 IPC 启动信号（守护进程亚毫秒级感知）

    即使 DB 暂时被锁，前端和守护进程也能通过共享内存和 IPC 立即开始工作。
    """
    loop = asyncio.get_running_loop()

    # ── 第一步：从共享内存快速校验小说是否存在（优先）──
    next_stage = None
    current_act = 0
    current_chapter_in_act = 0
    target_chapters = 1
    current_stage_str = "macro_planning"

    shared = _get_shared_state_for_novel(novel_id)
    if shared and shared.get("_updated_at"):
        # 共享内存有数据：零 DB IO 路径
        current_stage_str = shared.get("current_stage", "macro_planning")
        current_act = shared.get("current_act", 0) or 0
        current_chapter_in_act = shared.get("current_chapter_in_act", 0) or 0
        target_chapters = shared.get("target_chapters", 1) or 1

        # 计算下一阶段
        fresh_stages = {"planning", "macro_planning"}
        if current_stage_str in fresh_stages:
            next_stage = NovelStage.MACRO_PLANNING.value
        elif current_stage_str == "paused_for_review":
            # 幕下已有章节节点则直接写作，否则幕级规划
            if _has_chapter_nodes_under_current_act(novel_id, current_act):
                next_stage = NovelStage.WRITING.value
            else:
                next_stage = NovelStage.ACT_PLANNING.value
        else:
            next_stage = current_stage_str
    else:
        # ── 降级路径：共享内存无数据，必须读 DB（在线程池中执行）──
        def _start_read_sync():
            repo = get_novel_repository()
            n = repo.get_by_id(NovelId(novel_id))
            if not n:
                return None
            return {
                "current_stage": n.current_stage.value if hasattr(n.current_stage, 'value') else str(n.current_stage),
                "current_act": n.current_act or 0,
                "current_chapter_in_act": n.current_chapter_in_act or 0,
                "target_chapters": n.target_chapters or 1,
            }

        try:
            novel_data = await asyncio.wait_for(
                loop.run_in_executor(_SSE_THREAD_POOL, _start_read_sync),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(503, "数据库繁忙，请稍后重试")

        if novel_data is None:
            raise HTTPException(404, "小说不存在")

        current_stage_str = novel_data["current_stage"]
        current_act = novel_data["current_act"]
        current_chapter_in_act = novel_data["current_chapter_in_act"]
        target_chapters = novel_data["target_chapters"]

        fresh_stages = {"planning", "macro_planning"}
        if current_stage_str in fresh_stages:
            next_stage = NovelStage.MACRO_PLANNING.value
        elif current_stage_str == "paused_for_review":
            if _has_chapter_nodes_under_current_act(novel_id, current_act):
                next_stage = NovelStage.WRITING.value
            else:
                next_stage = NovelStage.ACT_PLANNING.value
        else:
            next_stage = current_stage_str

    # ── 第二步：立即写入共享内存（前端立即可见）──
    try:
        from interfaces.main import update_shared_novel_state
        update_shared_novel_state(novel_id,
            autopilot_status="running",
            current_stage=next_stage,
            current_act=current_act,
            current_chapter_in_act=current_chapter_in_act,
            current_beat_index=0,
            consecutive_error_count=0,
        )
        logger.debug("autopilot start: 已刷新共享内存状态 novel=%s", novel_id)
    except Exception as e:
        logger.debug("刷新共享内存失败（可忽略）: %s", e)

    # ── 第三步：异步持久化到 DB（不阻塞 API 返回）──
    def _start_persist_sync():
        """线程池中执行：DB 读取 + 写入（不阻塞事件循环）"""
        try:
            repo = get_novel_repository()
            novel = repo.get_by_id(NovelId(novel_id))
            if not novel:
                return
            novel.autopilot_status = AutopilotStatus.RUNNING
            novel.max_auto_chapters = body.max_auto_chapters
            novel.current_auto_chapters = novel.current_auto_chapters or 0
            novel.consecutive_error_count = 0

            fresh_stages_obj = {NovelStage.PLANNING, NovelStage.MACRO_PLANNING}
            if novel.current_stage in fresh_stages_obj:
                novel.current_stage = NovelStage.MACRO_PLANNING
            if novel.current_stage == NovelStage.PAUSED_FOR_REVIEW:
                novel.current_stage = _stage_after_review(novel)

            repo.save(novel)
            logger.info("autopilot start: novel_id=%s persisted RUNNING (DB)", novel_id)
        except Exception as e:
            logger.warning("autopilot start DB 持久化失败（共享内存已生效）: %s", e)

    loop.run_in_executor(_SSE_THREAD_POOL, _start_persist_sync)  # 🔥 不 await，fire-and-forget

    # ── 第四步：发布 IPC 启动信号 ──
    try:
        from application.engine.services.novel_stop_signal import publish_start_signal
        publish_start_signal(novel_id)
    except Exception as e:
        logger.debug("发布启动信号失败（可忽略，守护进程将通过 DB 降级路径感知）: %s", e)

    return {
        "success": True,
        "message": f"自动驾驶已启动，目标 {target_chapters} 章（保护上限 {body.max_auto_chapters} 章）",
        "autopilot_status": "running",
        "current_stage": next_stage,
        "target_chapters": target_chapters,
    }


@router.post("/{novel_id}/stop")
async def stop_autopilot(novel_id: str):
    """停止自动驾驶（IPC 零延迟版）

    双通道停止机制：
    1. mp.Event.set() → 守护进程亚毫秒级感知（主通道，零 DB 开销）
    2. DB UPDATE → 降级兜底（守护进程重启后仍能读到 STOPPED）

    SQLite 操作在线程池中执行，不阻塞 uvicorn 事件循环。

    幂等性：如果已经是 stopped 状态，直接返回成功，避免重复发布停止信号和 DB 写入。
    """
    # 🔥 幂等保护：检查共享内存状态，已是 stopped 则直接返回
    # 防止前端因响应延迟重复调 /stop 导致日志刷屏和 DB 竞争
    try:
        from interfaces.main import get_shared_novel_state
        shared = get_shared_novel_state(novel_id)
        if shared and shared.get("autopilot_status") == "stopped":
            logger.debug("autopilot stop: novel_id=%s 已是 stopped，跳过重复停止", novel_id)
            return {"success": True, "message": "自动驾驶已停止（幂等跳过）"}
    except Exception:
        pass  # 共享内存不可用时走正常流程

    # 通道 1：IPC 停止信号（亚毫秒级，零 DB 开销）
    try:
        from application.engine.services.novel_stop_signal import publish_stop_signal
        publish_stop_signal(novel_id)
        logger.info("autopilot stop: novel_id=%s IPC 停止信号已发布", novel_id)
    except Exception as e:
        logger.debug("发布 IPC 停止信号失败（将依赖 DB 降级路径）: %s", e)

    # 🔥 关键修复：立即更新共享内存状态，让 SSE 流能检测到状态变化
    # 否则 SSE 流从共享内存读取时仍看到 running，不会推送 autopilot_complete 事件
    try:
        from interfaces.main import update_shared_novel_state
        update_shared_novel_state(novel_id,
            autopilot_status="stopped",
        )
        logger.debug("autopilot stop: 已更新共享内存状态 novel=%s", novel_id)
    except Exception as e:
        logger.debug("更新共享内存失败（可忽略）: %s", e)

    # 通道 2：DB 持久化（降级兜底，守护进程重启后仍能读到 STOPPED）
    def _stop_sync():
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database

        db = get_database(get_db_path())
        db.execute(
            """UPDATE novels SET autopilot_status = 'stopped', updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (novel_id,),
        )
        db.commit()
        logger.info("autopilot stop: novel_id=%s committed STOPPED (DB 兜底)", novel_id)

    try:
        await asyncio.get_running_loop().run_in_executor(_SSE_THREAD_POOL, _stop_sync)
        return {"success": True, "message": "自动驾驶已停止"}
    except Exception as e:
        logger.warning("autopilot stop DB 写入失败, falling back: %s", e)
        # 🔥 修复：fallback 路径同样可能 database is locked，
        # IPC 信号（通道 1）已保证守护进程亚毫秒级停止，
        # DB 持久化只是兜底，失败时不应阻塞 API 返回
        try:
            repo = get_novel_repository()
            novel = repo.get_by_id(NovelId(novel_id))
            if novel:
                novel.autopilot_status = AutopilotStatus.STOPPED
                repo.save(novel)
                logger.info("autopilot stop: novel_id=%s committed STOPPED (fallback)", novel_id)
        except Exception as fallback_err:
            # fallback 也失败（大概率也是 database is locked），仅记日志
            # IPC 通道已确保停止信号送达，DB 兜底可延迟生效
            logger.warning(
                "autopilot stop fallback 也失败（IPC 通道已保证停止）: %s", fallback_err
            )
        return {"success": True, "message": "自动驾驶已停止（停止信号已通过 IPC 送达）"}


@router.post("/{novel_id}/resume")
async def resume_from_review(novel_id: str):
    """从人工审阅点恢复（PAUSED_FOR_REVIEW → RUNNING）（非阻塞版）

    架构优化：与 start_autopilot 一致
    1. 先从共享内存校验 + 计算下一阶段
    2. 立即写入共享内存（前端立即可见）
    3. 异步持久化到 DB（不阻塞事件循环）
    4. 发布 IPC 启动信号
    """
    loop = asyncio.get_running_loop()

    # ── 第一步：从共享内存校验当前状态 ──
    current_act = 0
    current_stage_str = ""

    shared = _get_shared_state_for_novel(novel_id)
    if shared and shared.get("_updated_at"):
        current_stage_str = shared.get("current_stage", "")
        current_act = shared.get("current_act", 0) or 0

        if current_stage_str != "paused_for_review":
            raise HTTPException(400, f"当前不在审阅等待状态（当前：{current_stage_str}）")
    else:
        # 降级路径：共享内存无数据，读 DB（在线程池中）
        def _resume_read_sync():
            repo = get_novel_repository()
            n = repo.get_by_id(NovelId(novel_id))
            if not n:
                return None
            return {
                "current_stage": n.current_stage.value if hasattr(n.current_stage, 'value') else str(n.current_stage),
                "current_act": n.current_act or 0,
            }

        try:
            novel_data = await asyncio.wait_for(
                loop.run_in_executor(_SSE_THREAD_POOL, _resume_read_sync),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(503, "数据库繁忙，请稍后重试")

        if novel_data is None:
            raise HTTPException(404, "小说不存在")

        current_stage_str = novel_data["current_stage"]
        current_act = novel_data["current_act"]

        if current_stage_str != "paused_for_review":
            raise HTTPException(400, f"当前不在审阅等待状态（当前：{current_stage_str}）")

    # 计算下一阶段
    if _has_chapter_nodes_under_current_act(novel_id, current_act):
        next_stage = NovelStage.WRITING.value
        msg = "已恢复：当前幕已有章节规划，进入正文撰写"
    else:
        next_stage = NovelStage.ACT_PLANNING.value
        msg = "已恢复：继续幕级规划"

    # ── 第二步：立即写入共享内存（前端立即可见）──
    try:
        from interfaces.main import update_shared_novel_state
        update_shared_novel_state(novel_id,
            autopilot_status="running",
            current_stage=next_stage,
            current_act=current_act,
        )
    except Exception as e:
        logger.debug("刷新共享内存失败（可忽略）: %s", e)

    # ── 第三步：异步持久化到 DB ──
    def _resume_persist_sync():
        try:
            repo = get_novel_repository()
            novel = repo.get_by_id(NovelId(novel_id))
            if not novel:
                return
            novel.autopilot_status = AutopilotStatus.RUNNING
            novel.current_stage = _stage_after_review(novel)
            repo.save(novel)
            logger.info("autopilot resume: novel_id=%s persisted (DB)", novel_id)
        except Exception as e:
            logger.warning("autopilot resume DB 持久化失败（共享内存已生效）: %s", e)

    loop.run_in_executor(_SSE_THREAD_POOL, _resume_persist_sync)  # 🔥 fire-and-forget

    # ── 第四步：发布 IPC 启动信号 ──
    try:
        from application.engine.services.novel_stop_signal import publish_start_signal
        publish_start_signal(novel_id)
    except Exception as e:
        logger.debug("发布启动信号失败（可忽略）: %s", e)

    logger.info("autopilot resume novel=%s -> %s", novel_id, next_stage)
    return {"success": True, "message": msg, "current_stage": next_stage}


@router.get("/{novel_id}/status")
async def get_autopilot_status(novel_id: str):
    """获取完整运行状态。

    🔥 核心架构优化：纯内存读取，纳秒级响应，永不阻塞事件循环。

    所有数据都从共享内存读取，完全不走 DB。
    这是"内存优先读取"架构的核心端点。
    """
    from application.engine.services.query_service import get_query_service

    query = get_query_service()
    status = query.get_novel_status(novel_id)

    if status is None:
        # 小说不在共享内存中，可能是不存在或未加载
        # 返回 404 而不是尝试读 DB（避免阻塞）
        raise HTTPException(404, "小说不存在或未加载")

    return status.to_dict()


@router.get("/{novel_id}/circuit-breaker")
async def get_circuit_breaker(novel_id: str):
    """
    熔断面板数据：基于小说落库的连续失败计数与自动驾驶状态。

    🔥 优化：从共享内存读取，不阻塞事件循环。
    """
    from application.engine.services.query_service import get_query_service

    query = get_query_service()
    state = query.get_novel_status(novel_id)

    if state is None:
        raise HTTPException(404, "小说不存在")

    error_count = state.consecutive_error_count
    ap = state.autopilot_status

    if ap == "error":
        breaker_status = "open"
    elif ap == "running" and 0 < error_count < PER_NOVEL_FAILURE_THRESHOLD:
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
    """清零连续失败计数；若因错误挂起则切回停止，需用户重新启动自动驾驶。

    🔥 优化：通过 StatePublisher 更新，避免直接 DB 操作。
    """
    from application.engine.services.state_publisher import get_state_publisher
    from application.engine.services.query_service import get_query_service

    query = get_query_service()
    state = query.get_novel_status(novel_id)

    if state is None:
        raise HTTPException(404, "小说不存在")

    publisher = get_state_publisher()

    # 更新状态
    new_status = "stopped" if state.autopilot_status == "error" else state.autopilot_status
    publisher.update_novel_state(
        novel_id,
        consecutive_error_count=0,
        autopilot_status=new_status,
    )

    return {"success": True, "message": "熔断计数已清零"}


@router.get("/{novel_id}/stream")
async def autopilot_log_stream(
    novel_id: str,
    after_seq: int = Query(0, ge=0, description="仅推送 seq 大于该值的守护进程日志行；重连时传入上次最后一条 seq"),
):
    """
    SSE 实时日志流（用于监控大盘）

    - log_line: API 进程内存环 + LOG_FILE 增量 tail（独立守护进程日志，按书目过滤）
    - beat_start / beat_complete / stage_change / progress 等：状态机摘要
    """
    novel_repo = get_novel_repository()
    chapter_repo = get_chapter_repository()

    async def event_generator():
        install_autopilot_log_ring_handler()

        # SSE 连接超时控制
        start_time = asyncio.get_running_loop().time()

        # 发送初始连接事件（前端可不写入时间线；metadata 用于工具栏「当前阶段」标签）
        loop = asyncio.get_running_loop()
        init_meta = await loop.run_in_executor(_SSE_THREAD_POOL, _log_stream_boot_meta_sync, novel_repo, novel_id)
        init_event = {
            "type": "connected",
            "message": "日志流已连接（含守护进程实时日志；阶段变更约 4s 去抖）",
            "timestamp": datetime.now().isoformat(),
            "metadata": init_meta,
        }
        yield f"data: {json.dumps(init_event, ensure_ascii=False)}\n\n"

        last_seq_cursor = after_seq
        replay_lines, last_seq_cursor = await loop.run_in_executor(
            _SSE_THREAD_POOL, _log_stream_replay_sync, novel_id, after_seq, last_seq_cursor
        )
        for line in replay_lines:
            yield line

        log_file_path = os.getenv("LOG_FILE", "logs/aitext.log")
        file_cursor = await loop.run_in_executor(
            _SSE_THREAD_POOL, _log_stream_file_cursor_init_sync, log_file_path, after_seq
        )

        last_beat = None
        heartbeat_counter = 0
        last_error_broadcast = -1
        complete_sent = False
        # 阶段变更去抖：同一阶段需连续 2 次轮询（约 4s）一致才推送，避免幕级规划↔待审阅 来回刷屏
        first_stage_poll = True
        last_emitted_stage: Optional[str] = None
        stage_pending: Optional[str] = None
        stage_pending_ticks = 0

        while True:
            try:
                # 连接超时检测
                if (loop.time() - start_time) > _SSE_MAX_LIFETIME_SECONDS:
                    logger.info("SSE log stream reached max lifetime, closing: novel=%s", novel_id)
                    break

                # 客户端断开检测
                if await _is_client_disconnected():
                    logger.debug("SSE log stream client disconnected: novel=%s", novel_id)
                    break

                # 🔥 加超时保护：DB 被锁时 2 秒超时，避免线程池阻塞
                try:
                    tick_result = await asyncio.wait_for(
                        loop.run_in_executor(
                            _SSE_THREAD_POOL,
                            _log_stream_io_tick_sync,
                            novel_repo,
                            chapter_repo,
                            novel_id,
                            log_file_path,
                            file_cursor,
                            last_seq_cursor,
                        ),
                        timeout=2.0,
                    )
                    novel, chapters_stats, file_lines, file_cursor, ring_batch, audit_events = tick_result
                except asyncio.TimeoutError:
                    logger.debug("SSE log stream tick 超时 novel=%s，跳过本轮 DB 查询", novel_id)
                    # 超时时只读日志文件和内存环（不碰 DB）
                    file_lines, file_cursor = read_incremental_log_file_lines(log_file_path, novel_id, file_cursor)
                    ring_batch = list(iter_new_for_novel(novel_id, last_seq_cursor, limit=200))
                    # 🔥 超时时也获取审计事件
                    from application.engine.services.streaming_bus import streaming_bus
                    stream_data = streaming_bus.get_chunks_and_events_batch(novel_id, max_chunks=200)
                    audit_events = stream_data.get("audit_events", [])
                    # 从共享内存读取降级状态
                    shared = _get_shared_state_for_novel_cached(novel_id)
                    if shared and shared.get("_updated_at"):
                        # 构造一个最小 novel 代理对象用于阶段检测
                        current_stage = shared.get("current_stage", "")
                        current_beat = shared.get("current_beat_index", 0) or 0
                        current_chapter_number = shared.get("_cached_current_chapter_number")
                    else:
                        current_stage = ""
                        current_beat = 0
                        current_chapter_number = None
                    # 降级处理：只推送日志，不推送进度
                    for item in file_lines:
                        ev = {
                            "type": "log_line",
                            "message": item["message"],
                            "timestamp": item["timestamp"],
                            "metadata": {
                                "seq": item["seq"],
                                "level": item["level"],
                                "logger": item["logger"],
                                "source": "file",
                            },
                        }
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                        last_seq_cursor = max(last_seq_cursor, item["seq"])
                    for e in ring_batch:
                        ev = {
                            "type": "log_line",
                            "message": shorten_log_message(e.message),
                            "timestamp": e.timestamp_iso,
                            "metadata": {
                                "seq": e.seq,
                                "level": e.level,
                                "logger": e.logger_name,
                            },
                        }
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                        last_seq_cursor = max(last_seq_cursor, e.seq)
                    # 🔥 推送审计事件
                    for audit_event in audit_events:
                        event = {
                            "type": "audit_event",
                            "message": _audit_event_message(audit_event["event_type"], audit_event["data"]),
                            "timestamp": datetime.now().isoformat(),
                            "metadata": {
                                "event_type": audit_event["event_type"],
                                "data": audit_event["data"],
                            },
                        }
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(2)
                    continue

                if not novel:
                    # 🔥 novel=None 时先查共享内存，避免 DB 临时不可用时误断 SSE
                    shared_chk = _get_shared_state_for_novel_cached(novel_id)
                    if shared_chk and shared_chk.get("autopilot_status") in ("running", "paused_for_review"):
                        logger.debug("SSE log stream novel=None but shared shows running, keep alive: novel=%s", novel_id)
                        await asyncio.sleep(3.0)
                        continue
                    logger.info("SSE log stream novel not found, closing: novel=%s", novel_id)
                    break

                # 🔥 chapters_stats 是轻量聚合结果，不再是全量章节列表
                current_chapter_number = None
                if chapters_stats and chapters_stats.get('current_chapter_number'):
                    current_chapter_number = chapters_stats['current_chapter_number']
                elif chapters_stats is None:
                    # 非写作阶段：从共享内存读取当前章节号
                    shared = _get_shared_state_for_novel_cached(novel_id)
                    if shared:
                        current_chapter_number = shared.get("_cached_current_chapter_number")
                chapter_label = f"第 {current_chapter_number} 章 · " if current_chapter_number else ""

                for item in file_lines:
                    ev = {
                        "type": "log_line",
                        "message": item["message"],
                        "timestamp": item["timestamp"],
                        "metadata": {
                            "seq": item["seq"],
                            "level": item["level"],
                            "logger": item["logger"],
                            "source": "file",
                        },
                    }
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    last_seq_cursor = max(last_seq_cursor, item["seq"])

                for e in ring_batch:
                    ev = {
                        "type": "log_line",
                        "message": shorten_log_message(e.message),
                        "timestamp": e.timestamp_iso,
                        "metadata": {
                            "seq": e.seq,
                            "level": e.level,
                            "logger": e.logger_name,
                        },
                    }
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    last_seq_cursor = max(last_seq_cursor, e.seq)

                # 🔥 推送审计事件
                for audit_event in audit_events:
                    event = {
                        "type": "audit_event",
                        "message": _audit_event_message(audit_event["event_type"], audit_event["data"]),
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "event_type": audit_event["event_type"],
                            "data": audit_event["data"],
                        },
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                current_stage = novel.current_stage.value
                current_beat = getattr(novel, "current_beat_index", 0) or 0
                # current_beat 为守护进程 0-based「下一节拍索引」；面向用户统一用 1-based 展示

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
                    done_1based = int(last_beat) + 1
                    next_1based = int(current_beat) + 1
                    event = {
                        "type": "beat_complete",
                        "message": f"{chapter_label}第 {act_display} 幕 · 节拍 {done_1based} 已生成完毕",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "beat_index": last_beat,
                            "beat_index_1based": done_1based,
                            "act": novel.current_act,
                            "act_display": act_display,
                            "chapter_number": current_chapter_number,
                        },
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                    # 新 beat 开始
                    event = {
                        "type": "beat_start",
                        "message": f"{chapter_label}第 {act_display} 幕 · 正在生成节拍 {next_1based}",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "beat_index": current_beat,
                            "beat_index_1based": next_1based,
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

                # 托管进入终态：单连接只发一次「自动驾驶已停止」事件；不断开 SSE，继续 tail 日志与心跳，
                # 避免前端误以为「未连接」且无法再看后续守护进程日志。
                terminal_states = {"stopped", "error", "completed"}
                if novel.autopilot_status.value in terminal_states:
                    if not complete_sent:
                        complete_sent = True
                        st = novel.autopilot_status.value
                        event = {
                            "type": "autopilot_complete",
                            "message": f"自动驾驶{_autopilot_status_zh(st)}",
                            "timestamp": datetime.now().isoformat(),
                            "metadata": {
                                "status": st,
                                "status_label": _autopilot_status_zh(st),
                                "tail": True,
                            },
                        }
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 运行中：定期推送进度快照（仅用于前端进度条，不写时间线刷屏）
                if novel.autopilot_status.value == AutopilotStatus.RUNNING.value:
                    # 🔥 优先使用轻量聚合结果，不再遍历章节列表
                    tgt = novel.target_chapters or 1
                    if chapters_stats:
                        n_done = chapters_stats.get('completed_count', 0)
                        tw = int(chapters_stats.get('total_words', 0)) if chapters_stats.get('total_words') else 0
                        current_chapter_number = chapters_stats.get('current_chapter_number')
                    else:
                        # 审计/规划阶段：从共享内存读取统计
                        shared = _get_shared_state_for_novel_cached(novel_id)
                        n_done = shared.get("_cached_completed_chapters", 0) if shared else 0
                        tw = int(shared.get("_cached_total_words", 0)) if shared else 0
                        current_chapter_number = shared.get("_cached_current_chapter_number") if shared else None
                    pct = round(n_done / tgt * 100, 1) if tgt else 0.0
                    stage_zh = _stage_name_zh(current_stage)
                    act_display = (novel.current_act or 0) + 1
                    beat_1based = int(current_beat) + 1
                    # ★ 从共享内存读取细化子步骤字段
                    _shared_sub = _get_shared_state_for_novel_cached(novel_id) or {}
                    writing_substep = _shared_sub.get("writing_substep", "")
                    writing_substep_label = _shared_sub.get("writing_substep_label", "")
                    total_beats = _shared_sub.get("total_beats", 0)
                    beat_focus = _shared_sub.get("beat_focus", "")
                    beat_target_words = _shared_sub.get("beat_target_words", 0)
                    accumulated_words = _shared_sub.get("accumulated_words", 0)
                    chapter_target_words = _shared_sub.get("chapter_target_words", 0)
                    context_tokens = _shared_sub.get("context_tokens", 0)

                    # 构建细化的进度消息
                    substep_hint = f" · {writing_substep_label}" if writing_substep_label else ""
                    beat_progress = f"节拍 {beat_1based}/{total_beats}" if total_beats else f"节拍 {beat_1based}"
                    word_progress = ""
                    if accumulated_words and chapter_target_words:
                        word_pct = min(100, int(accumulated_words / chapter_target_words * 100))
                        word_progress = f" · {accumulated_words}/{chapter_target_words}字({word_pct}%)"

                    progress_event = {
                        "type": "progress",
                        "message": (
                            f"全书 {n_done}/{tgt} 章 · 约 {tw} 字 · "
                            f"第 {act_display} 幕 · {beat_progress} · {stage_zh}{substep_hint}"
                        ),
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "completed_chapters": n_done,
                            "target_chapters": tgt,
                            "progress_pct": pct,
                            "total_words": tw,
                            "current_act": novel.current_act,
                            "act_display": act_display,
                            "current_beat_index": current_beat,
                            "current_beat_index_1based": beat_1based,
                            "stage": current_stage,
                            "stage_label": stage_zh,
                            "chapter_number": current_chapter_number,
                            "autopilot_status": novel.autopilot_status.value,
                            "autopilot_status_label": _autopilot_status_zh(
                                novel.autopilot_status.value
                            ),
                            # ★ V9 细化字段
                            "writing_substep": writing_substep,
                            "writing_substep_label": writing_substep_label,
                            "total_beats": int(total_beats or 0),
                            "beat_focus": beat_focus,
                            "beat_target_words": int(beat_target_words or 0),
                            "accumulated_words": int(accumulated_words or 0),
                            "chapter_target_words": int(chapter_target_words or 0),
                            "context_tokens": int(context_tokens or 0),
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
    """SSE 实时推送正在写作的章节内容（优化版 v2）

    推送事件类型：
    - chapter_chunk: 增量文字片段
    - chapter_start: 开始写新章节
    - autopilot_stopped: 自动驾驶停止

    优化点：
    1. 批量获取 chunks 减少 SSE 事件数量
    2. 审阅状态时快速断开，避免占用资源
    3. 不再调用 clear()，避免数据丢失
    4. 更快的轮询间隔，提高响应速度
    """
    novel_repo = get_novel_repository()
    chapter_repo = get_chapter_repository()

    async def event_generator():
        loop = asyncio.get_running_loop()
        start_time = loop.time()
        # 发送初始连接事件
        init_event = {
            "type": "connected",
            "message": "章节内容流已连接",
            "timestamp": datetime.now().isoformat()
        }
        yield f"data: {json.dumps(init_event, ensure_ascii=False)}\n\n"

        last_chapter_number = None
        heartbeat_counter = 0
        empty_poll_count = 0
        MAX_EMPTY_POLLS = 24  # 连续空轮询约 12 秒后检查状态

        try:
            while True:
                # 连接超时检测
                if (loop.time() - start_time) > _SSE_MAX_LIFETIME_SECONDS:
                    logger.info("SSE chapter stream reached max lifetime, closing: novel=%s", novel_id)
                    break

                # 客户端断开检测
                if await _is_client_disconnected():
                    logger.debug("SSE chapter stream client disconnected: novel=%s", novel_id)
                    break
                # 🔥 加超时保护：DB 被锁时 2 秒超时，避免线程池被阻塞线程耗尽
                try:
                    novel, chapters, chunks = await asyncio.wait_for(
                        loop.run_in_executor(
                            _SSE_THREAD_POOL, _chapter_stream_tick_sync, novel_repo, chapter_repo, novel_id, 50
                        ),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    # DB 被锁时只读 chunks（不碰 DB），前端不会卡死
                    logger.debug("SSE chapter stream tick 超时 novel=%s，跳过 DB", novel_id)
                    chunks = _chapter_stream_chunks_sync(novel_id, 50)
                    novel = None
                    # 从共享内存判断是否仍在运行
                    shared = _get_shared_state_for_novel_cached(novel_id)
                    if shared and shared.get("autopilot_status") in ("stopped", "error", "completed"):
                        event = {
                            "type": "autopilot_stopped",
                            "message": f"自动驾驶已停止: {shared['autopilot_status']}",
                            "timestamp": datetime.now().isoformat(),
                        }
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        break
                    # 仍然推送 chunks，让前端看到正文流
                    if chunks:
                        combined = "".join(chunks)
                        if combined:
                            beat_idx = (shared.get("current_beat_index", 0) or 0) if shared else 0
                            event = {
                                "type": "chapter_chunk",
                                "message": "",
                                "timestamp": datetime.now().isoformat(),
                                "metadata": {
                                    "chunk": combined,
                                    "beat_index": beat_idx,
                                },
                            }
                            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(poll_interval if 'poll_interval' in dir() else 0.8)
                    continue
                if not novel:
                    # 🔥 novel=None 时先查共享内存确认小说是否真的不存在，
                    # 避免 DB 被锁/慢查询时误断 SSE 导致前端疯狂重连
                    shared_chk = _get_shared_state_for_novel_cached(novel_id)
                    if shared_chk and shared_chk.get("autopilot_status") in ("running", "paused_for_review"):
                        # 共享内存显示仍在运行，DB 临时不可用，保持 SSE
                        logger.debug("SSE chapter stream novel=None but shared shows running, keep alive: novel=%s", novel_id)
                        await asyncio.sleep(poll_interval if 'poll_interval' in dir() else 3.0)
                        continue
                    # 共享内存也无数据，小说可能真的不存在，断开
                    logger.info("SSE chapter stream novel not found, closing: novel=%s", novel_id)
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

                # 审阅状态时断开 SSE，避免卡界面
                if novel.current_stage.value == "paused_for_review":
                    event = {
                        "type": "paused_for_review",
                        "message": "等待审阅确认",
                        "timestamp": datetime.now().isoformat(),
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    break

                # 检测新章节开始
                if novel.current_stage.value == "writing" and chapters:
                    _st = lambda c: c.status.value if hasattr(c.status, "value") else c.status
                    drafts = sorted(
                        [c for c in chapters if _st(c) == "draft"],
                        key=lambda c: c.number
                    )
                    if drafts:
                        chapter_number = drafts[0].number
                        # 发送章节开始事件
                        if last_chapter_number is None or chapter_number != last_chapter_number:
                            event = {
                                "type": "chapter_start",
                                "message": f"开始写第 {chapter_number} 章",
                                "timestamp": datetime.now().isoformat(),
                                "metadata": {"chapter_number": chapter_number},
                            }
                            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                            logger.debug(f"[SSE] chapter_start: 第 {chapter_number} 章")
                            # 注意：不再调用 clear()，避免丢失队列中的数据
                        last_chapter_number = chapter_number

                if chunks:
                    empty_poll_count = 0
                    # 合并小 chunks 为单个事件，减少 SSE 事件数量
                    combined = "".join(chunks)
                    if combined:
                        # 🔥 优先从共享状态读取 beat_index（实时更新），而非 DB
                        shared = _get_shared_state_for_novel_cached(novel_id)
                        beat_idx = (shared.get("current_beat_index", 0) or 0) if shared else 0
                        event = {
                            "type": "chapter_chunk",
                            "message": "",
                            "timestamp": datetime.now().isoformat(),
                            "metadata": {
                                "chunk": combined,
                                "beat_index": beat_idx,
                            },
                        }
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                else:
                    empty_poll_count += 1
                    # 连续空轮询过多时检查状态
                    if empty_poll_count >= MAX_EMPTY_POLLS:
                        empty_poll_count = 0
                        # 🔥 优先从共享内存检查状态（零 DB IO），避免 DB 被锁时阻塞线程池
                        shared_chk = _get_shared_state_for_novel_cached(novel_id)
                        if shared_chk and shared_chk.get("autopilot_status") in terminal_states:
                            break
                        # 共享内存没有数据时才查 DB（加超时保护）
                        if not shared_chk or not shared_chk.get("_updated_at"):
                            try:
                                novel_chk = await asyncio.wait_for(
                                    loop.run_in_executor(
                                        _SSE_THREAD_POOL, novel_repo.get_by_id, NovelId(novel_id)
                                    ),
                                    timeout=1.0,
                                )
                                if not novel_chk or novel_chk.autopilot_status.value in terminal_states:
                                    break
                            except asyncio.TimeoutError:
                                pass  # DB 被锁，跳过，下轮再查

                # 心跳（每 10 次循环约 5 秒）
                heartbeat_counter += 1
                if heartbeat_counter >= 10:
                    heartbeat_event = {
                        "type": "heartbeat",
                        "message": "keepalive",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(heartbeat_event, ensure_ascii=False)}\n\n"
                    heartbeat_counter = 0

                # 轮询间隔：写作阶段 800ms，审计/规划阶段 3 秒（审计期间无 chunks 推送，
                # 无需高频轮询；减少 DB 查询可显著降低线程池压力和锁竞争）
                current_stage_val = novel.current_stage.value if novel else "writing"
                poll_interval = 3.0 if current_stage_val in ("auditing", "macro_planning", "act_planning") else 0.8
                await asyncio.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Chapter stream error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/{novel_id}/events")
async def autopilot_events(novel_id: str):
    """SSE 实时状态推送（每 3 秒，带 2 秒 DB 查询超时保护）。"""
    novel_repo = get_novel_repository()
    chapter_repo = get_chapter_repository()

    async def event_generator():
        loop = asyncio.get_running_loop()
        start_time = loop.time()
        while True:
            try:
                # 连接超时检测
                if (loop.time() - start_time) > _SSE_MAX_LIFETIME_SECONDS:
                    logger.info("SSE events stream reached max lifetime, closing: novel=%s", novel_id)
                    break
                if await _is_client_disconnected():
                    break

                # 🔥 防御性编程：SSE tick 也加 2 秒超时，防止 DB 锁阻塞线程池
                try:
                    payload, should_break = await asyncio.wait_for(
                        loop.run_in_executor(
                            _SSE_THREAD_POOL, _autopilot_events_tick_sync, novel_repo, chapter_repo, novel_id
                        ),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("⏱️ SSE events tick 超时 novel=%s，发送降级心跳", novel_id)
                    payload = {
                        "type": "heartbeat",
                        "current_stage": "syncing",
                        "audit_progress": None,
                        "_degraded": True,
                        "_message": "数据同步中...",
                    }
                    should_break = False

                if payload is None:
                    break
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if should_break:
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
    from application.engine.services.streaming_bus import get_stream_queue, streaming_bus
    import multiprocessing as mp

    queue = get_stream_queue()
    current_process = mp.current_process()

    # 尝试读取一条消息（非阻塞）
    sample_msg = None
    queue_size = 0
    if queue is not None:
        try:
            # 尝试获取队列大小
            queue_size = streaming_bus.get_queue_size()
            # 读取一条消息作为样本
            sample_msg = queue.get_nowait()
            # 把消息放回去
            queue.put_nowait(sample_msg)
        except Exception as e:
            sample_msg = f"Error: {e}"

    return {
        "novel_id": novel_id,
        "current_process": current_process.name,
        "is_daemon": current_process.daemon,
        "queue_available": queue is not None,
        "queue_size": queue_size,
        "sample_message": sample_msg,
    }


@router.get("/system/resources")
async def get_system_resources():
    """获取系统资源状态（线程池、缓存、队列等）"""
    return _rm.health_check()


@router.get("/system/cache/stats")
async def get_cache_stats():
    """获取缓存统计信息"""
    return _SHARED_STATE_CACHE.get_stats()


@router.post("/system/cache/cleanup")
async def cleanup_cache():
    """手动清理过期缓存"""
    cleaned = _SHARED_STATE_CACHE.cleanup_expired()
    return {"cleaned": cleaned}


@router.post("/system/resources/cleanup-idle")
async def cleanup_idle_resources(idle_seconds: float = 300):
    """清理空闲资源"""
    cleaned = _rm.cleanup_idle(idle_seconds)
    return {"cleaned": cleaned}


@router.get("/debug/thread-pool")
async def debug_thread_pool():
    """调试：线程池状态"""
    import threading
    executor = _SSE_THREAD_POOL._resource if hasattr(_SSE_THREAD_POOL, '_resource') else _SSE_THREAD_POOL
    return {
        "thread_pool_type": type(executor).__name__,
        "max_workers": getattr(executor, '_max_workers', 'unknown'),
        "threads_count": len([t for t in threading.enumerate() if 'sse-io' in t.name]),
        "all_threads": [{"name": t.name, "alive": t.is_alive()} for t in threading.enumerate()],
    }


@router.get("/debug/shared-state")
async def debug_shared_state(novel_id: str = None):
    """调试：共享内存状态"""
    from interfaces.main import _get_shared_state
    import multiprocessing as mp

    try:
        state = _get_shared_state()
        keys = list(state.keys()) if state else []
        result = {
            "state_available": state is not None,
            "keys_count": len(keys),
            "keys": keys[:20],  # 只显示前20个
            "process_name": mp.current_process().name,
        }

        # 如果指定了 novel_id，显示详细信息
        if novel_id:
            key = f"novel:{novel_id}"
            novel_state = dict(state.get(key, {}))
            result["novel_state"] = novel_state
            result["novel_updated_at"] = novel_state.get("_updated_at")
            result["novel_age_seconds"] = time.time() - novel_state.get("_updated_at", 0) if novel_state.get("_updated_at") else None

        # 守护进程心跳
        daemon_heartbeat = state.get("_daemon_heartbeat")
        result["daemon_heartbeat"] = daemon_heartbeat
        result["daemon_heartbeat_age"] = time.time() - daemon_heartbeat if daemon_heartbeat else None
        result["daemon_alive"] = (time.time() - daemon_heartbeat) < 60.0 if daemon_heartbeat else False

        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/db-lock")
async def debug_db_lock():
    """调试：检查 DB 锁状态"""
    import sqlite3
    from application.paths import get_db_path
    from pathlib import Path

    db_path = get_db_path()
    db_path_obj = Path(db_path) if isinstance(db_path, str) else db_path

    result = {
        "db_path": str(db_path_obj),
        "db_exists": db_path_obj.exists(),
        "wal_exists": db_path_obj.with_suffix('.db-wal').exists(),
        "shm_exists": db_path_obj.with_suffix('.db-shm').exists(),
    }

    # 尝试获取锁（带超时）
    if db_path_obj.exists():
        try:
            conn = sqlite3.connect(str(db_path_obj), timeout=0.5)
            conn.execute("BEGIN IMMEDIATE")
            conn.commit()
            conn.close()
            result["lock_test"] = "success"
        except sqlite3.OperationalError as e:
            result["lock_test"] = f"locked: {e}"
        except Exception as e:
            result["lock_test"] = f"error: {e}"

    # 检查是否有 -journal 文件（回滚日志）
    journal_path = db_path_obj.with_suffix('.db-journal')
    result["journal_exists"] = journal_path.exists()

    return result


@router.get("/debug/all")
async def debug_all(novel_id: str = None):
    """调试：综合诊断"""
    import threading
    import sqlite3
    from interfaces.main import _get_shared_state
    from application.paths import get_db_path
    from pathlib import Path

    # 线程池状态
    executor = _SSE_THREAD_POOL._resource if hasattr(_SSE_THREAD_POOL, '_resource') else _SSE_THREAD_POOL
    thread_info = {
        "max_workers": getattr(executor, '_max_workers', 'unknown'),
        "sse_threads": len([t for t in threading.enumerate() if 'sse-io' in t.name]),
        "total_threads": threading.active_count(),
    }

    # 共享内存状态
    try:
        state = _get_shared_state()
        shared_info = {
            "available": state is not None,
            "keys": list(state.keys())[:10] if state else [],
        }
        daemon_heartbeat = state.get("_daemon_heartbeat") if state else None
        shared_info["daemon_alive"] = (time.time() - daemon_heartbeat) < 60.0 if daemon_heartbeat else False
        shared_info["daemon_heartbeat_age"] = time.time() - daemon_heartbeat if daemon_heartbeat else None
    except Exception as e:
        shared_info = {"error": str(e)}

    # DB 状态
    db_path_obj = Path(get_db_path())
    db_info = {
        "exists": db_path_obj.exists(),
        "wal_exists": db_path_obj.with_suffix('.db-wal').exists(),
    }
    if db_path_obj.exists():
        try:
            conn = sqlite3.connect(str(db_path_obj), timeout=0.5)
            conn.execute("SELECT 1 FROM novels LIMIT 1")
            conn.close()
            db_info["accessible"] = True
        except Exception as e:
            db_info["accessible"] = False
            db_info["error"] = str(e)

    # 指定小说状态
    novel_info = None
    if novel_id:
        try:
            shared = _get_shared_state_for_novel_cached(novel_id)
            if shared:
                novel_info = {
                    "in_shared_memory": True,
                    "updated_at": shared.get("_updated_at"),
                    "age_seconds": time.time() - shared.get("_updated_at", 0) if shared.get("_updated_at") else None,
                    "cached_chapters": shared.get("_cached_completed_chapters"),
                    "stage": shared.get("current_stage"),
                    "status": shared.get("autopilot_status"),
                    "beat_index": shared.get("current_beat_index"),
                }
            else:
                novel_info = {"in_shared_memory": False}
        except Exception as e:
            novel_info = {"error": str(e)}

    return {
        "timestamp": time.time(),
        "thread_pool": thread_info,
        "shared_memory": shared_info,
        "database": db_info,
        "novel": novel_info,
        "cache_stats": _SHARED_STATE_CACHE.get_stats(),
    }

