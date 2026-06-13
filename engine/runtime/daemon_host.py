"""DaemonHostMixin — 守护进程基础设施 (Phase 7)

持久化、共享内存、停止信号、审计/写作 helper。
AutopilotDaemon 通过继承获得这些方法；runtime delegates 通过 host 协议调用。
"""
from __future__ import annotations

import time
import logging
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.novel.entities.chapter import ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from application.ai.trace_context import ensure_trace
from domain.ai.value_objects.prompt import Prompt
from application.engine.services.context_builder import ContextBuilder
from application.engine.services.background_task_service import BackgroundTaskService, TaskType
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from application.engine.services.style_constraint_builder import build_style_summary
from application.ai.llm_output_sanitize import strip_reasoning_artifacts
from application.ai.prose_fragment_aggregator import aggregate_inline_prose_fragments
from application.ai.llm_retry_policy import LLM_MAX_TOTAL_ATTEMPTS
from application.workflows.beat_continuation import format_prior_draft_for_prompt
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.word_count import WordCount
from domain.novel.value_objects.generation_preferences import GenerationPreferences
from domain.structure.story_node import StoryNode

logger = logging.getLogger(__name__)


def _coerce_word_count_to_int(wc: Any) -> int:
    """章节 word_count 可能为 int 或 WordCount 值对象。"""
    if wc is None:
        return 0
    if isinstance(wc, WordCount):
        return wc.value
    return int(wc)


VOICE_REWRITE_MAX_ATTEMPTS = LLM_MAX_TOTAL_ATTEMPTS
VOICE_REWRITE_THRESHOLD = 0.68
VOICE_WARNING_DEFAULT_THRESHOLD = 0.75


def init_daemon_dependencies(
    host: Any,
    *,
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
    chapter_workflow=None,
    aftermath_pipeline=None,
    volume_summary_service=None,
    foreshadowing_repository=None,
    knowledge_service=None,
    use_story_pipeline_for_writing: bool | None = None,
) -> None:
    """注入守护进程依赖 — AutopilotDaemon / StoryPipelineRunner 共用（Phase 8）"""
    if use_story_pipeline_for_writing is None:
        from engine.runtime.writing_delegate import is_story_pipeline_writing_enabled

        use_story_pipeline_for_writing = is_story_pipeline_writing_enabled()
    host.novel_repository = novel_repository
    host.llm_service = llm_service
    host.context_builder = context_builder
    host.background_task_service = background_task_service
    host.planning_service = planning_service
    host.story_node_repo = story_node_repo
    host.chapter_repository = chapter_repository
    host.poll_interval = poll_interval
    host.voice_drift_service = voice_drift_service
    host.circuit_breaker = circuit_breaker
    host.chapter_workflow = chapter_workflow
    host.aftermath_pipeline = aftermath_pipeline
    host.volume_summary_service = volume_summary_service
    host.foreshadowing_repository = foreshadowing_repository
    host.knowledge_service = knowledge_service
    host.use_story_pipeline_for_writing = use_story_pipeline_for_writing

    host._beat_exhausted_rewrite_count = {}
    host._pending_chapter_micro_beats = {}
    host._pending_story_pipeline_aftermath = {}

    if not host.volume_summary_service and llm_service and story_node_repo:
        try:
            from application.blueprint.services.volume_summary_service import VolumeSummaryService

            host.volume_summary_service = VolumeSummaryService(
                llm_service=llm_service,
                story_node_repository=story_node_repo,
                chapter_repository=chapter_repository,
                foreshadowing_repository=foreshadowing_repository,
            )
        except ImportError:
            host.volume_summary_service = None


class DaemonHostMixin:
    """守护进程基础设施 — 供 AutopilotDaemon 继承"""

    def _push_persistence_command(self, command_type: str, payload: Dict) -> bool:
        """推送持久化命令到队列（CQRS 单一写入者模式）

        守护进程不直接写 DB，而是将命令推入队列，
        由 API 进程的消费者线程统一写入，彻底消除锁竞争。
        """
        try:
            from application.engine.services.persistence_queue import get_persistence_queue
            pq = get_persistence_queue()
            return pq.push(command_type, payload)
        except Exception as e:
            logger.debug(f"持久化队列不可用，降级到直接写 DB: {e}")
            return False


    def _get_active_novels(self) -> List[Novel]:
        """获取所有活跃小说（DB + 共享内存，避免 DB 与前端状态短暂不一致时漏捞）"""
        running = self.novel_repository.find_by_autopilot_status(
            AutopilotStatus.RUNNING.value
        )
        seen = {n.novel_id.value for n in running}

        try:
            from application.engine.services.shared_state_repository import (
                get_shared_state_repository,
            )

            shared_repo = get_shared_state_repository()
            for nid in shared_repo.get_all_novel_ids():
                if nid in seen:
                    continue
                state = shared_repo.get_novel_state(nid)
                if not state or state.autopilot_status != AutopilotStatus.RUNNING.value:
                    continue
                novel = self.novel_repository.get_by_id(NovelId(nid))
                if novel is None:
                    continue
                novel.autopilot_status = AutopilotStatus.RUNNING
                running.append(novel)
                seen.add(nid)
                logger.info(
                    "[%s] 共享内存为 running、DB 未同步，已纳入守护进程处理队列",
                    nid,
                )
        except Exception as e:
            logger.debug("合并共享内存 running 小说失败（可忽略）: %s", e)

        return running


    def _write_daemon_heartbeat(self) -> None:
        """写入守护进程心跳到共享内存，让前端判断后端是否存活。

        成熟方案做法：
        - 守护进程每轮循环写入时间戳（~5s 一次）
        - API 进程的 /status 读取心跳时间戳
        - 前端若连续 60s 未看到心跳更新，可显示"后端忙碌或网络延迟"

        🔥 改进：同时更新所有活跃小说的共享内存 _updated_at，
        避免 LLM 调用期间共享状态过期导致前端显示"后端处理中"。
        """
        now = time.time()
        try:
            import sys
            shared = sys.modules.get("__shared_state")
            if shared is not None:
                shared["_daemon_heartbeat"] = now
                # 🔥 同时刷新所有活跃小说的 _updated_at，防止共享状态过期
                for key in list(shared.keys()):
                    if key.startswith("novel:") and isinstance(shared[key], dict):
                        shared[key]["_updated_at"] = now
                return
        except Exception:
            pass
        try:
            import multiprocessing
            if multiprocessing.current_process().daemon:
                return
        except Exception:
            return
        # 降级：通过主进程模块
        try:
            from interfaces.runtime_state import update_shared_novel_state
            # 用特殊 key 写入心跳（非小说级别，而是全局级别）
            from interfaces.runtime_state import _get_shared_state
            state = _get_shared_state()
            state["_daemon_heartbeat"] = now
        except Exception:
            pass


    def _save_novel_ephemeral(self, novel: Novel) -> bool:
        """🔥 用独立短连接保存 novel 状态到 DB（替代 novel_repository.save()）。

        核心问题：novel_repository.save() 使用线程本地长连接，在守护进程
        （独立进程）中会长时间持有 SQLite 写锁，阻塞 API 进程。
        改为独立短连接：打开 → 写入 → 提交 → 关闭，写锁持有时间极短。

        字段必须与 SqliteNovelRepository.save() 的 ON CONFLICT UPDATE 完全一致，
        否则会遗漏更新导致数据丢失（如张力、审计快照等）。
        """
        import json as _json

        fields = {
            "autopilot_status": novel.autopilot_status.value if isinstance(novel.autopilot_status, AutopilotStatus) else str(novel.autopilot_status),
            "current_stage": novel.current_stage.value if hasattr(novel.current_stage, 'value') else str(novel.current_stage),
            "current_act": novel.current_act or 0,
            "current_chapter_in_act": novel.current_chapter_in_act or 0,
            "current_beat_index": novel.current_beat_index or 0,
            "current_auto_chapters": novel.current_auto_chapters or 0,
            "target_chapters": novel.target_chapters or 0,
            "target_words_per_chapter": novel.target_words_per_chapter or 2500,
            "consecutive_error_count": novel.consecutive_error_count or 0,
            "last_chapter_tension": novel.last_chapter_tension or 0,
            # 🔥 needs_review 是计算字段（由 current_stage == paused_for_review 推导），
            # novels 表无此列，不能写入 DB，否则会导致 "no such column: needs_review" 错误
            # 使整条审计落盘失败。前端通过 current_stage 自行推导 needs_review。
            "beats_completed": getattr(novel, 'beats_completed', 0) or 0,
            # 审计快照字段（与 SqliteNovelRepository.save() 对齐）
            "auto_approve_mode": 1 if getattr(novel, 'auto_approve_mode', False) else 0,
            "last_audit_chapter_number": getattr(novel, 'last_audit_chapter_number', None),
            "last_audit_similarity": getattr(novel, 'last_audit_similarity', None),
            "last_audit_drift_alert": 1 if getattr(novel, 'last_audit_drift_alert', False) else 0,
            "last_audit_narrative_ok": 1 if getattr(novel, 'last_audit_narrative_ok', True) else 0,
            "last_audit_at": getattr(novel, 'last_audit_at', None),
            "last_audit_vector_stored": 1 if getattr(novel, 'last_audit_vector_stored', False) else 0,
            "last_audit_foreshadow_stored": 1 if getattr(novel, 'last_audit_foreshadow_stored', False) else 0,
            "last_audit_triples_extracted": 1 if getattr(novel, 'last_audit_triples_extracted', False) else 0,
            "last_audit_quality_scores": _json.dumps(getattr(novel, 'last_audit_quality_scores', None)) if getattr(novel, 'last_audit_quality_scores', None) else None,
            "last_audit_issues": _json.dumps(getattr(novel, 'last_audit_issues', None)) if getattr(novel, 'last_audit_issues', None) else None,
            "audit_progress": getattr(novel, 'audit_progress', None),
        }

        set_clauses = [f"{k} = ?" for k in fields.keys()]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        sql = f"UPDATE novels SET {', '.join(set_clauses)} WHERE id = ?"
        params = list(fields.values()) + [novel.novel_id.value]

        # CQRS：全部由 API 消费者串行落库，守护进程不再直连写第二路
        ok = self._queue_sql(sql, params)
        if not ok:
            logger.warning("持久化队列写入失败 novel=%s（无短连接兜底）", novel.novel_id.value)
        return ok


    def _save_chapter_ephemeral(self, novel_id: str, chapter_number: int,
                                 content: str = None, status: str = None,
                                 word_count: int = None,
                                 tension_score: float = None,
                                 plot_tension: float = None,
                                 emotional_tension: float = None,
                                 pacing_tension: float = None) -> bool:
        """🔥 保存章节状态——CQRS 统一写入通道。

        默认推持久化队列（零锁竞争）；
        仅 completed 状态为关键路径（需同步落库），用短连接直接写。
        """
        set_parts = []
        params = []

        if content is not None:
            set_parts.append("content = ?")
            params.append(content)
        if status is not None:
            set_parts.append("status = ?")
            params.append(status)
        if word_count is not None:
            set_parts.append("word_count = ?")
            params.append(word_count)
        if tension_score is not None:
            set_parts.append("tension_score = ?")
            params.append(tension_score)
        if plot_tension is not None:
            set_parts.append("plot_tension = ?")
            params.append(plot_tension)
        if emotional_tension is not None:
            set_parts.append("emotional_tension = ?")
            params.append(emotional_tension)
        if pacing_tension is not None:
            set_parts.append("pacing_tension = ?")
            params.append(pacing_tension)

        if not set_parts:
            return True

        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        sql = f"UPDATE chapters SET {', '.join(set_parts)} WHERE novel_id = ? AND number = ?"
        params.extend([novel_id, chapter_number])

        # 全部经由持久化队列；completed 亦不直连 DB，杜绝第二写者。
        return self._queue_sql(sql, params)


    def _queue_sql(self, sql: str, params: tuple | list = ()) -> bool:
        """🔥 CQRS 统一写入通道——将 SQL 写操作推入持久化队列。

        由 API 进程的消费者线程串行执行，从根本上消除多进程写锁竞争。
        守护进程不再直接写 DB，所有写操作走此通道。
        """
        from application.engine.services.persistence_queue import PersistenceCommandType
        # params 可能是 tuple 或 list，统一为 list（mp.Queue 要求 JSON 可序列化）
        params_list = list(params) if params else []
        return self._push_persistence_command(
            PersistenceCommandType.EXECUTE_SQL.value,
            {"sql": sql, "params": params_list},
        )


    def _patch_novel_ephemeral(
        self,
        novel_id: NovelId,
        fields: Dict[str, Any],
        **kwargs: Any,
    ) -> bool:
        """增量 UPDATE novels——统一持久化队列，与单写者内核一致。"""
        from domain.novel.entities.novel import AutopilotStatus as _APS, NovelStage as _NS

        _ = kwargs

        if not fields:
            return True

        processed: Dict[str, Any] = {}
        for key, value in fields.items():
            if isinstance(value, _APS):
                processed[key] = value.value
            elif isinstance(value, _NS):
                processed[key] = value.value
            elif isinstance(value, bool):
                processed[key] = 1 if value else 0
            elif isinstance(value, (dict, list)):
                import json as _json

                processed[key] = _json.dumps(value, ensure_ascii=False)
            else:
                processed[key] = value

        processed["updated_at"] = datetime.now(timezone.utc).isoformat()

        set_clauses = [f"{key} = ?" for key in processed.keys()]
        values = list(processed.values()) + [novel_id.value]

        sql = f"UPDATE novels SET {', '.join(set_clauses)} WHERE id = ?"
        return self._queue_sql(sql, values)


    def _push_patch_to_queue(self, novel_id: NovelId, fields: Dict[str, Any]) -> None:
        """将增量更新推入持久化队列——CQRS 统一写入通道的兼容入口。

        现在底层统一走 _queue_sql → EXECUTE_SQL，此方法保留作为调用点兼容，
        处理枚举/bool/JSON 转换后构建 SQL 并推队列。
        """
        from domain.novel.entities.novel import AutopilotStatus as _APS, NovelStage as _NS
        from application.engine.services.persistence_queue import PersistenceCommandType

        # 枚举转换（与 _patch_novel_ephemeral 一致）
        processed = {}
        for key, value in fields.items():
            if isinstance(value, _APS):
                processed[key] = value.value
            elif isinstance(value, _NS):
                processed[key] = value.value
            elif isinstance(value, bool):
                processed[key] = 1 if value else 0
            elif isinstance(value, (dict, list)):
                import json as _json
                processed[key] = _json.dumps(value, ensure_ascii=False)
            else:
                processed[key] = value

        processed["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"{key} = ?" for key in processed.keys()]
        values = list(processed.values()) + [novel_id.value]
        sql = f"UPDATE novels SET {', '.join(set_clauses)} WHERE id = ?"

        ok = self._queue_sql(sql, values)
        if ok:
            logger.debug("[novel-%s] 增量更新已推队列", novel_id.value)
        else:
            logger.warning("[novel-%s] 推队列失败，数据可能丢失", novel_id.value)


    def _read_chapter_stats_ephemeral(
        self, novel_id: str, timeout: float = 5.0
    ) -> Optional[Tuple[int, int, int]]:
        """与 /autopilot/status DB 路径一致的章节聚合（短连接只读）。

        用于在审计完成、章节落库后刷新共享内存缓存，避免 _cache_stats_to_shared_memory
        用 current_auto_chapters=0 覆盖真实统计导致前端长期显示 0/0/总字数 0。
        """
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database

        try:
            db = get_database(get_db_path())
            agg_rows = db.fetch_all(
                "SELECT status, SUM(LENGTH(COALESCE(content,''))) as total_wc "
                "FROM chapters WHERE novel_id = ? GROUP BY status",
                (novel_id,),
            )
            completed_count = 0
            in_manuscript_count = 0
            total_words = 0
            for r in agg_rows:
                s = r["status"] or ""
                wc = r["total_wc"] or 0
                total_words += int(wc)
                if s == "completed":
                    completed_count += 1
                    in_manuscript_count += 1
                elif s == "draft":
                    in_manuscript_count += 1
            return (completed_count, in_manuscript_count, total_words)
        except Exception as e:
            logger.debug("章节统计短连接读取失败 novel=%s: %s", novel_id, e)
            return None


    def _read_autopilot_status_ephemeral(self, novel_id: NovelId) -> Optional[AutopilotStatus]:
        """用独立 SQLite 连接读 autopilot_status。

        主仓储连接在 asyncio 与 asyncio.to_thread、或后台线程里并发用时，同一 sqlite3 连接
        跨线程未定义行为，且长连接可能看不到他处已提交的 STOPPED。短连接每次打开可读 WAL 最新提交。

        优化：使用 WAL 模式和更短的超时，提高响应速度。
        """
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database

        db = get_database(get_db_path())
        row = db.fetch_one(
            "SELECT autopilot_status FROM novels WHERE id = ?",
            (novel_id.value,),
        )
        if not row:
            return None
        raw = row["autopilot_status"]
        try:
            return AutopilotStatus(raw)
        except ValueError:
            return AutopilotStatus.STOPPED


    def _merge_autopilot_status_from_db(self, novel: Novel) -> None:
        """用户点「停止」只改 DB；写库前必须合并，否则会覆盖 STOPPED。"""
        status = self._read_autopilot_status_ephemeral(novel.novel_id)
        if status is not None:
            novel.autopilot_status = status


    def _is_still_running(self, novel: Novel) -> bool:
        """检查自动驾驶是否仍在运行（IPC 优先 + DB 降级）。

        检测优先级：
        1. 本地 threading.Event（亚微秒级，零 I/O 开销）—— 主通道
        2. DB 降级（仅本地 Event 未设置时使用，如守护进程重启后冷启动）

        无论哪个通道检测到 STOPPED，都立即返回 False。
        """
        # 通道 1：本地停止信号（亚微秒级）
        try:
            from application.engine.services.novel_stop_signal import is_novel_stopped
            if is_novel_stopped(novel.novel_id.value) or is_novel_stopped("__all__"):
                novel.autopilot_status = AutopilotStatus.STOPPED
                return False
        except Exception:
            pass  # 模块未初始化时静默降级

        # 通道 2：DB 降级（守护进程重启后冷启动时仍需要）
        self._merge_autopilot_status_from_db(novel)
        return novel.autopilot_status == AutopilotStatus.RUNNING


    def _cleanup_stale_stop_signals(self, active_novels: List[Novel]) -> None:
        """🔥 清理残留的停止信号

        当用户"停止"→"开始"后，DB 中 autopilot_status 已恢复为 RUNNING，
        但守护进程内的 threading.Event 可能仍为 set 状态（mp.Queue 的
        start_signal 还没来得及被消费）。

        这个方法在每轮主循环中执行，确保 DB 为 RUNNING 的小说
        不会被残留的本地停止信号阻塞。
        """
        try:
            from application.engine.services.novel_stop_signal import is_novel_stopped, clear_local_novel_stop
            for novel in active_novels:
                nid = novel.novel_id.value
                if is_novel_stopped(nid):
                    # DB 中是 RUNNING，但本地 Event 为 set → 清除残留信号
                    # 先确认 DB 确实是 RUNNING（避免误清真正的停止信号）
                    db_status = self._read_autopilot_status_ephemeral(novel.novel_id)
                    if db_status == AutopilotStatus.RUNNING:
                        clear_local_novel_stop(nid)
                        logger.info(
                            f"[{nid}] 🔧 清除残留停止信号（DB=RUNNING，但本地 Event 仍为 set）"
                        )
        except Exception as e:
            logger.debug(f"清理残留停止信号失败（可忽略）: {e}")


    def _novel_is_running(self, novel_id: NovelId) -> bool:
        """流式轮询用：不修改内存 novel；检查是否仍为 RUNNING（IPC 优先 + DB 降级）。

        优先检查本地 threading.Event（零 I/O 开销），仅当未设置时降级到 DB 轮询。
        """
        # 通道 1：本地停止信号
        try:
            from application.engine.services.novel_stop_signal import is_novel_stopped
            if is_novel_stopped(novel_id.value) or is_novel_stopped("__all__"):
                return False
        except Exception:
            pass

        # 通道 2：DB 降级
        return self._novel_is_running_in_db(novel_id)


    def _novel_is_running_in_db(self, novel_id: NovelId) -> bool:
        """DB 降级路径：独立连接读是否仍为 RUNNING（仅当 mp.Event 未初始化时使用）。"""
        status = self._read_autopilot_status_ephemeral(novel_id)
        return status == AutopilotStatus.RUNNING


    def _flush_novel(self, novel: Novel) -> None:
        """关键阶段立即写库，避免下一轮轮询仍读到旧 stage（重复幕级规划 / 重复日志）。

        使用 patch 增量更新（仅写入变化的字段），减少写事务持锁时间。

        🔥 CQRS 架构：_patch_novel_ephemeral 推持久化队列（EXECUTE_SQL），
        由 API 进程消费者线程串行执行，与单写者内核一致。
        同步非统计字段到共享内存，避免 /status 长期读到过时阶段信息。
        章节聚合（完稿/书稿/总字数）由章节落库与审计完成路径写入 _cached_*。
        """
        self._merge_autopilot_status_from_db(novel)
        # 关键字段增量更新（不再全量 save 30+ 字段）
        patch_fields = dict(
            autopilot_status=novel.autopilot_status,
            current_stage=novel.current_stage,
            current_act=novel.current_act,
            current_chapter_in_act=novel.current_chapter_in_act,
            current_beat_index=novel.current_beat_index,
            beats_completed=novel.beats_completed,
            consecutive_error_count=novel.consecutive_error_count,
            current_auto_chapters=novel.current_auto_chapters,
        )
        # 审计快照字段（审计阶段写入，避免丢失）
        if getattr(novel, "last_audit_chapter_number", None) is not None:
            patch_fields["last_audit_chapter_number"] = novel.last_audit_chapter_number
            patch_fields["last_audit_similarity"] = getattr(novel, "last_audit_similarity", None)
            patch_fields["last_audit_drift_alert"] = getattr(novel, "last_audit_drift_alert", False)
            patch_fields["last_audit_narrative_ok"] = getattr(novel, "last_audit_narrative_ok", True)
            patch_fields["last_audit_vector_stored"] = getattr(novel, "last_audit_vector_stored", False)
            patch_fields["last_audit_foreshadow_stored"] = getattr(novel, "last_audit_foreshadow_stored", False)
            patch_fields["last_audit_triples_extracted"] = getattr(novel, "last_audit_triples_extracted", False)
            patch_fields["last_audit_at"] = getattr(novel, "last_audit_at", None)
        # 张力值
        if getattr(novel, "last_chapter_tension", None) is not None:
            patch_fields["last_chapter_tension"] = novel.last_chapter_tension

        # 🔥 CQRS：优先推持久化队列（零锁竞争），_patch_novel_ephemeral 内部
        # 默认走 _queue_sql → EXECUTE_SQL 命令，由 API 进程消费者串行执行
        ok = self._patch_novel_ephemeral(novel.novel_id, patch_fields)

        # 同步阶段、节拍等非聚合字段到共享内存（完稿/书稿/总字数仅在落库与审计节点写入 _cached_*）
        self._cache_stats_to_shared_memory(novel)


    def _save_novel_state(self, novel: Novel) -> None:
        """与 _flush_novel 相同语义：增量 patch 替代全量 save。"""
        self._flush_novel(novel)


    def _sync_novel_current_act_from_chapter_story_node(self, novel: Novel, chapter_node: StoryNode) -> None:
        """按章节在结构树上的父幕校正 ``novel.current_act``（0-based，且约定等于 ``act.number - 1``）。

        ``_find_next_unwritten_chapter_async`` 按全书章号扫描，而 ``current_act`` 仅在幕规划/
        幕写完时推进；若章节曾错误挂到别幕（或预生成高编号幕），会出现「正在写第 23 章却
        显示第 4 幕」等割裂。写作/审计前以**真实父幕**为准同步一次。
        """
        if not chapter_node or not getattr(chapter_node, "parent_id", None):
            return
        nid = novel.novel_id.value
        try:
            all_nodes = self.story_node_repo.get_by_novel_sync(nid)
            by_id = {n.id: n for n in all_nodes}
            parent = by_id.get(chapter_node.parent_id)
            if not parent or parent.node_type.value != "act":
                return
            act_serial = int(parent.number)  # story_nodes.act.number，全书幕序号
            desired = act_serial - 1
            if novel.current_act != desired:
                logger.info(
                    f"[{nid}] 校正 current_act：{novel.current_act} → {desired} "
                    f"（第{chapter_node.number}章挂于幕 act.number={act_serial} {parent.title!r}）"
                )
                novel.current_act = desired
                try:
                    self._push_patch_to_queue(novel.novel_id, {"current_act": desired})
                except Exception as pe:
                    logger.debug(f"[{nid}] 校正 current_act 落库入队失败（可忽略）: {pe}")
        except Exception as e:
            logger.debug(f"[{nid}] 按章节校正 current_act 失败（可忽略）: {e}")


    def _sync_novel_current_act_from_chapter_number(self, novel: Novel, chapter_num: int) -> None:
        """由全局章号查找 story 节点后同步 ``current_act``。"""
        if chapter_num is None or chapter_num < 1:
            return
        try:
            all_nodes = self.story_node_repo.get_by_novel_sync(novel.novel_id.value)
            ch_node = next(
                (
                    n
                    for n in all_nodes
                    if n.node_type.value == "chapter" and int(n.number) == int(chapter_num)
                ),
                None,
            )
            if ch_node:
                self._sync_novel_current_act_from_chapter_story_node(novel, ch_node)
        except Exception as e:
            logger.debug(f"[{novel.novel_id.value}] 按章号校正 current_act 失败（可忽略）: {e}")


    def _cache_stats_to_shared_memory(self, novel: Novel) -> None:
        """将「非统计」状态同步到共享内存（节拍 / flush 高频路径）。

        注意：不要在此写入 _cached_completed_chapters / _cached_manuscript_chapters /
        _cached_total_words / _cached_current_chapter_number。本方法在每次 patch 后调用；
        若在规划或节拍阶段用不完整的 novel 字段覆盖，会把审计刚对齐的缓存冲掉，
        前端会长期显示完稿 0、书稿 0、总字数 0。

        章节聚合统计仅在章节落库后与审计完成时，通过 _read_chapter_stats_ephemeral
        显式写入共享内存。
        """
        nid = novel.novel_id.value
        # 🔥 查询当前幕的标题和描述（供前端展示）
        current_act_title = None
        current_act_description = None
        try:
            if novel.current_act is not None:
                target_act_number = novel.current_act + 1  # 1-indexed
                all_nodes = self.story_node_repo.get_by_novel_sync(nid)
                act_nodes = sorted(
                    [n for n in all_nodes if n.node_type.value == "act"],
                    key=lambda n: n.number
                )
                target_act = next((n for n in act_nodes if n.number == target_act_number), None)
                if target_act:
                    current_act_title = target_act.title
                    current_act_description = target_act.description
        except Exception as e:
            logger.debug(f"[{nid}] 查询幕标题/描述失败（可忽略）: {e}")

        try:
            self._update_shared_state(
                nid,
                current_stage=novel.current_stage.value,
                current_act=novel.current_act,
                current_act_title=current_act_title,
                current_act_description=current_act_description,
                current_chapter_in_act=novel.current_chapter_in_act,
                current_beat_index=novel.current_beat_index or 0,
                autopilot_status=novel.autopilot_status.value,
                consecutive_error_count=novel.consecutive_error_count or 0,
                target_chapters=novel.target_chapters,
                target_words_per_chapter=getattr(novel, 'target_words_per_chapter', 2500) or 2500,
                auto_approve_mode=getattr(novel, 'auto_approve_mode', False),
                last_chapter_tension=getattr(novel, 'last_chapter_tension', 0) or 0,
                current_auto_chapters=novel.current_auto_chapters,
            )
        except Exception as e:
            logger.debug(f"[{nid}] 缓存统计到共享内存失败（可忽略）: {e}")

    # ── 故事线 / 编年史 共享内存同步 ───────────────────────────────


    def _sync_storylines_to_shared_memory(self, novel_id: str) -> None:
        """🔥 宏观规划完成后重新加载故事线到共享内存，确保甘特图/故事线列表实时可见。

        纯 DB 读取 + 内存写入，毫秒级，不阻塞事件循环。
        """
        try:
            from application.engine.services.state_bootstrap import StateBootstrap
            bootstrap = StateBootstrap()
            count = len(bootstrap._load_storylines(novel_id))
            logger.debug(f"[{novel_id}] 同步故事线到共享内存: {count} 条")
        except Exception as e:
            logger.debug(f"[{novel_id}] 同步故事线失败（可忽略）: {e}")

    async def _extract_chapter_bridge(self, novel_id: str, chapter_number: int, content: str) -> None:
        """🔗 衔接引擎：审计完成后提取章节桥段（5 维衔接锚点），供下一章首段衔接使用。

        策略：
        - 用 LLM 从章节末尾 ~1500 字提取：悬念钩子、情感余韵、场景状态、角色位置、未完成动作
        - 持久化到 chapter_bridges 表
        - 下一章写作时由 context_budget_allocator 的 T0 层自动注入衔接指令
        - 约 ~300 token 输入 + ~200 token 输出，成本极低
        """
        try:
            from application.engine.services.chapter_bridge_service import ChapterBridgeService
            from application.paths import get_db_path

            svc = ChapterBridgeService(
                llm_service=self.llm_service,
                db_path=str(get_db_path()),
            )
            if svc.get_bridge(novel_id, chapter_number):
                logger.debug(
                    f"[{novel_id}] 桥段已存在，跳过重复提取 ch={chapter_number}"
                )
                return
            bridge = await svc.extract_bridge(novel_id, chapter_number, content)
            logger.info(
                f"[{novel_id}] 🔗 桥段提取完成 ch={chapter_number} "
                f"hook={'有' if bridge.suspense_hook else '无'} "
                f"emotion={'有' if bridge.emotional_residue else '无'} "
                f"scene={'有' if bridge.scene_state else '无'}"
            )
        except Exception as e:
            logger.warning(f"[{novel_id}] 桥段提取失败（不影响主流程）ch={chapter_number}: {e}")

    async def _run_anti_ai_audit(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> Any:
        """🛡️ Anti-AI 审计管线：对生成的章节进行 AI 味检测与审计。

        执行流程：
        1. 使用 ClicheScanner 扫描 AI 味模式
        2. 使用 AntiAIAuditor 生成审计报告
        3. 使用 AntiAIMetricsService 计算指标快照
        4. 使用 AntiAILearningService 学习新模式
        5. 将审计结果持久化到日志

        此方法为异步包装，实际扫描为同步操作。
        失败不影响主流程，返回 None；成功返回报告对象（供章末闸门判定）。
        """
        try:
            import asyncio
            loop = asyncio.get_event_loop()

            # 在线程池中执行同步扫描
            report = await loop.run_in_executor(
                None,
                self._sync_anti_ai_audit,
                novel_id,
                chapter_number,
                content,
            )

            if report:
                logger.info(
                    f"[{novel_id}] 🛡️ Anti-AI 审计完成 ch={chapter_number} "
                    f"score={report.metrics.severity_score} "
                    f"assessment={report.metrics.overall_assessment} "
                    f"hits={report.metrics.total_hits} "
                    f"critical={report.metrics.critical_hits}"
                )

                # 如果严重级别过高，记录警告
                if report.metrics.overall_assessment in ("中等", "严重"):
                    logger.warning(
                        f"[{novel_id}] 🛡️ 章节 {chapter_number} AI味过重 "
                        f"(score={report.metrics.severity_score}, "
                        f"assessment={report.metrics.overall_assessment})，"
                        f"建议：{'; '.join(report.recommendations[:2])}"
                    )
            return report

        except Exception as e:
            logger.warning(f"[{novel_id}] Anti-AI 审计失败（不影响主流程）ch={chapter_number}: {e}")
        return None


    def _sync_anti_ai_audit(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ):
        """同步执行 Anti-AI 审计。"""
        from application.audit.services.anti_ai_audit import get_anti_ai_auditor
        from application.audit.services.anti_ai_metrics import get_anti_ai_metrics_service
        from application.audit.services.anti_ai_learning import get_anti_ai_learning_service

        # 1. 审计扫描
        auditor = get_anti_ai_auditor()
        chapter_id = f"ch-{chapter_number}"
        report = auditor.scan_chapter(chapter_id, content)

        # 2. 计算指标
        metrics_svc = get_anti_ai_metrics_service()
        snapshot = metrics_svc.compute_snapshot(
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            content=content,
            hits=report.hits,
        )

        # 3. 学习新模式
        learning_svc = get_anti_ai_learning_service()
        learning_svc.analyze_chapter_audit(
            novel_id=novel_id,
            chapter_number=chapter_number,
            content=content,
            hits=report.hits,
        )

        # 4. 持久化审计结果到数据库
        try:
            from infrastructure.persistence.database.sqlite_anti_ai_audit_repository import SqliteAntiAiAuditRepository
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            repo = SqliteAntiAiAuditRepository(db)
            repo.upsert(
                novel_id=novel_id,
                chapter_number=chapter_number,
                total_hits=report.metrics.total_hits,
                critical_hits=report.metrics.critical_hits,
                warning_hits=report.metrics.warning_hits,
                info_hits=report.metrics.info_hits,
                severity_score=report.metrics.severity_score,
                overall_assessment=report.metrics.overall_assessment,
                hit_density=snapshot.hit_density,
                critical_density=snapshot.critical_density,
                category_distribution=report.metrics.category_distribution,
                top_patterns=report.metrics.top_patterns,
                recommendations=report.recommendations,
                improvement_suggestions=report.improvement_suggestions,
                hits_detail=[
                    {
                        "pattern": h.pattern,
                        "text": h.text,
                        "start": h.start,
                        "end": h.end,
                        "severity": h.severity,
                        "category": h.category,
                        "replacement_hint": h.replacement_hint,
                    }
                    for h in report.hits
                ],
            )
            logger.debug(
                f"[{novel_id}] 🛡️ Anti-AI 审计结果已持久化 ch={chapter_number}"
            )
        except Exception as persist_err:
            logger.warning(
                f"[{novel_id}] Anti-AI 审计结果持久化失败（不影响主流程）ch={chapter_number}: {persist_err}"
            )

        return report

    async def _continuity_self_check(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> str:
        """🔗 衔接自检：检查章节首段与前章桥段的衔接度，低于阈值则自动修整。

        仅在非第 1 章时触发。约 ~200 token 的轻量 LLM 调用。
        如果衔接度 < 0.6，自动修整首段（最多 2 轮）。
        """
        try:
            from application.engine.services.chapter_bridge_service import ChapterBridgeService
            from application.paths import get_db_path

            svc = ChapterBridgeService(
                llm_service=self.llm_service,
                db_path=str(get_db_path()),
            )
            prev_bridge = svc.get_prev_chapter_bridge(novel_id, chapter_number)
            if not prev_bridge:
                logger.debug(f"[{novel_id}] 无前章桥段，跳过衔接自检 ch={chapter_number}")
                return content

            result = await svc.check_continuity(novel_id, chapter_number, content, prev_bridge)
            logger.info(
                f"[{novel_id}] 🔗 衔接自检 ch={chapter_number} score={result.score:.2f}"
                + (f" issues={result.issues}" if result.issues else "")
            )

            # 衔接度低时告警；只有低于策略的自动修整阈值才改写正文。
            if svc.policy.needs_attention(result.score) and result.issues:
                logger.warning(
                    f"[{novel_id}] 🔗 衔接度低 ({result.score:.2f}) ch={chapter_number}"
                )
            if svc.should_auto_fix_opening(result) and result.issues:
                logger.warning(
                    f"[{novel_id}] 🔗 低于自动修整阈值，修整首段 ch={chapter_number}"
                )
                fixed_content = await svc.auto_fix_opening(
                    novel_id,
                    chapter_number,
                    content,
                    prev_bridge,
                    result,
                    max_rounds=svc.policy.max_fix_rounds,
                )
                if fixed_content != content:
                    logger.info(
                        f"[{novel_id}] 🔗 首段修整完成 ch={chapter_number} "
                        f"原={len(content)}字→新={len(fixed_content)}字"
                    )
                    return fixed_content
                else:
                    logger.info(f"[{novel_id}] 首段修整未改变内容 ch={chapter_number}")
        except Exception as e:
            logger.warning(f"[{novel_id}] 衔接自检失败（不影响主流程）ch={chapter_number}: {e}")

        return content

    def _sync_chronicles_to_shared_memory(self, novel_id: str) -> None:
        """🔥 审计完成后重新构建编年史缓存（Bible timeline_notes + snapshots + chapters），确保全息编年史实时可见。

        纯内存读取 + 聚合写入，纳秒级，不阻塞事件循环。
        """
        try:
            from application.engine.services.state_bootstrap import StateBootstrap
            bootstrap = StateBootstrap()
            count = len(bootstrap._load_chronicles(novel_id))
            logger.debug(f"[{novel_id}] 同步编年史到共享内存: {count} 行")
        except Exception as e:
            logger.debug(f"[{novel_id}] 同步编年史失败（可忽略）: {e}")

    @staticmethod
    def _beats_to_planned_micro_beats(beats: List[Any]) -> List[Dict[str, Any]]:
        """供共享内存 /status 与前端侧栏展示的指挥器节拍快照。"""
        from application.engine.services.beat_projection import planned_micro_beats_from_beats

        return planned_micro_beats_from_beats(beats)

    @staticmethod
    def _beat_sheet_to_plan_json(beat_sheet: Optional[Any]) -> Optional[Dict[str, Any]]:
        """将仓储 BeatSheet 转为 ``build_chapter_execution_plan_async`` 的 beat_sheet_json。"""
        from application.engine.services.beat_projection import beat_sheet_to_plan_json

        return beat_sheet_to_plan_json(beat_sheet)

    async def _get_beat_sheet_for_chapter(self, novel_id: str, chapter_number: int) -> Optional[Any]:
        """获取章节的 BeatSheet（规划阶段的预估字数）

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            BeatSheet 对象或 None
        """
        try:
            # 获取章节 ID
            chapter = self.chapter_repository.get_by_novel_and_number(
                NovelId(novel_id), chapter_number
            )
            if not chapter:
                return None

            # 尝试从仓储获取 BeatSheet
            from infrastructure.persistence.database.sqlite_beat_sheet_repository import SqliteBeatSheetRepository
            from infrastructure.persistence.database.connection import get_database

            beat_sheet_repo = SqliteBeatSheetRepository(get_database())
            # 🔥 get_by_chapter_id 是 async 方法，必须 await
            beat_sheet = await beat_sheet_repo.get_by_chapter_id(chapter.id)

            if beat_sheet and beat_sheet.scenes:
                return beat_sheet

        except Exception as e:
            logger.debug(f"获取 BeatSheet 失败: {e}")

        return None


    def _latest_completed_chapter_number(self, novel_id: NovelId) -> Optional[int]:
        """已完结章节的最大章节号（与故事树全局章节号一致）。

        🔥 性能优化：使用轻量 SQL 查询，不加载章节内容。
        原来用 list_by_novel 会加载所有章节的 content 字段（可能数百 KB），
        在 DB 锁竞争时会阻塞很久。
        """
        try:
            db = self.chapter_repository.db if hasattr(self.chapter_repository, 'db') else None
            if db is not None:
                row = db.fetch_one(
                    "SELECT MAX(number) as max_num FROM chapters WHERE novel_id = ? AND status = 'completed'",
                    (novel_id.value,)
                )
                if row and row['max_num']:
                    return row['max_num']
                return None
        except Exception:
            pass  # 降级到原方法

        # 降级：原来的方法
        chapters = self.chapter_repository.list_by_novel(novel_id)
        completed = [c for c in chapters if c.status == ChapterStatus.COMPLETED]
        if not completed:
            return None
        return max(c.number for c in completed)


    def _count_completed_chapters(self, novel_id: NovelId) -> int:
        """轻量 COUNT 查询：只返回已完成章节数，不加载全部章节对象。

        用于审计阶段的全书完成检测，替代 list_by_novel() 以减少 DB 锁持有时间
        和内存开销（103 章时 list_by_novel 加载 103 个完整 Chapter 对象含正文，
        而本方法只返回一个整数）。
        """
        try:
            db = self.chapter_repository.db if hasattr(self.chapter_repository, 'db') else None
            if db is not None:
                row = db.fetch_one(
                    "SELECT COUNT(*) as cnt FROM chapters WHERE novel_id = ? AND status = 'completed'",
                    (novel_id.value,)
                )
                return row['cnt'] if row else 0
        except Exception:
            pass
        # 降级：使用原有方法
        chapters = self.chapter_repository.list_by_novel(novel_id)
        return sum(1 for c in chapters if c.status == ChapterStatus.COMPLETED)


    def _publish_audit_event(self, novel_id: str, event_type: str, data: Optional[Dict] = None) -> None:
        """发布审计事件到流式总线

        Args:
            novel_id: 小说 ID
            event_type: 事件类型
                - "audit_start": 审计开始
                - "audit_voice_check": 文风预检
                - "audit_voice_result": 文风预检结果
                - "audit_aftermath": 章后管线
                - "audit_tension": 张力打分
                - "audit_tension_result": 张力打分结果
                - "audit_complete": 审计完成
            data: 事件数据
        """
        try:
            from application.engine.services.streaming_bus import streaming_bus
            streaming_bus.publish_audit_event(novel_id, event_type, data)
        except Exception as e:
            logger.debug(f"[{novel_id}] 发布审计事件失败: {e}")


    def _update_shared_state(self, novel_id: str, **fields) -> None:
        """将实时状态写入共享内存（供 API 与其他进程读取，不经由 SQLite）。

        守护进程高频写入阶段、审计进度、张力等；关键节点再落盘 novels/chapters。
        章节聚合 _cached_* 仅在落库、审计完成时写入，供 DB 被锁时 /status 降级使用；
        正常情况下 /status 会对完稿/书稿/总字数做短超时 DB 聚合并与共享字段合并。
        """
        # 🔥 确保 novel_id 始终在数据中
        fields["novel_id"] = novel_id

        try:
            # 优先尝试从主进程注入的共享状态
            import sys
            shared = sys.modules.get("__shared_state")
            if shared is not None:
                key = f"novel:{novel_id}"
                current = dict(shared.get(key, {}))
                current.update(fields)
                current["_updated_at"] = time.time()
                # 🔥 同时更新守护进程心跳
                shared["_daemon_heartbeat"] = time.time()
                shared[key] = current
                return
        except Exception:
            pass
        try:
            import multiprocessing
            if multiprocessing.current_process().daemon:
                return
        except Exception:
            return

        # 降级：直接通过主进程模块的函数写入（开发环境单进程时）
        try:
            from interfaces.runtime_state import update_shared_novel_state
            update_shared_novel_state(novel_id, **fields)
        except Exception:
            pass

    async def _call_with_timeout(
        self,
        coro,
        timeout: float,
        novel_id: str = "",
        label: str = "",
        timeout_default=None,
    ):
        """为 LLM 调用加超时保护 + 停止信号响应，避免 API 卡住或用户停止后仍在等待。

        双重保护：
        1. asyncio.wait_for 超时保护——防止 LLM API 无限等待
        2. 停止信号监听——用户点击停止后，5 秒内终止当前 LLM 调用

        Args:
            coro: awaitable 协程对象
            timeout: 超时秒数
            novel_id: 小说 ID（用于写共享状态和检查停止信号）
            label: 调用标签（用于日志）
            timeout_default: 超时/停止时的显式默认返回值
        """
        # ── 并行：LLM 调用 + 停止信号监听 ──
        stop_detected = asyncio.Event()

        async def _watch_stop():
            """监听停止信号，检测到后设置事件（双通道：IPC 优先 + 队列消费）"""
            while not stop_detected.is_set():
                await asyncio.sleep(0.2)  # 200ms 检查间隔（🔥 从 100ms 放宽，减少 CPU 开销）
                # 通道 1：本地 threading.Event
                try:
                    from application.engine.services.novel_stop_signal import is_novel_stopped
                    if is_novel_stopped(novel_id) or is_novel_stopped("__all__"):
                        stop_detected.set()
                        return
                except Exception:
                    pass
                # 通道 2：主动消费 mp.Queue
                try:
                    from application.engine.services.streaming_bus import streaming_bus
                    streaming_bus.consume_control_signals(novel_id)
                except Exception:
                    pass

        watch_task = None
        if novel_id:
            watch_task = asyncio.create_task(_watch_stop())

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)

            # LLM 调用正常完成，但检查是否在等待期间收到了停止信号
            if stop_detected.is_set():
                logger.info(f"[{novel_id}] {label} 完成但停止信号已触发，丢弃结果")
                return timeout_default

            return result

        except asyncio.TimeoutError:
            logger.warning(
                f"[{novel_id}] ⏱️ {label} 超时（{timeout}s），使用显式默认值: {timeout_default}"
            )
            if novel_id:
                self._update_shared_state(
                    novel_id,
                    _last_timeout_label=label,
                    _last_timeout_at=time.time(),
                )
            return timeout_default
        except Exception as e:
            logger.warning(f"[{novel_id}] {label} 异常: {e}，使用显式默认值")
            return timeout_default
        finally:
            stop_detected.set()
            if watch_task is not None:
                watch_task.cancel()
                try:
                    await watch_task
                except asyncio.CancelledError:
                    pass


    def _get_voice_service(self):
        """优先复用章后管线里的 voice service，避免配置分叉。"""
        if self.aftermath_pipeline and getattr(self.aftermath_pipeline, "_voice", None):
            return getattr(self.aftermath_pipeline, "_voice")
        return self.voice_drift_service


    def _similarity_below_warning_threshold(self, similarity_score: Any) -> bool:
        """展示告警阈值：宽松，用于提示。"""
        if similarity_score is None:
            return False
        try:
            from application.analyst.services.voice_drift_service import DRIFT_ALERT_THRESHOLD
            return float(similarity_score) < float(DRIFT_ALERT_THRESHOLD)
        except Exception:
            return float(similarity_score) < VOICE_WARNING_DEFAULT_THRESHOLD


    def _should_attempt_voice_rewrite(self, drift_result: Dict[str, Any]) -> bool:
        """自动修文阈值：严格，仅对明显偏离的当前章触发。"""
        similarity = drift_result.get("similarity_score")
        if similarity is None:
            return False
        try:
            return float(similarity) < VOICE_REWRITE_THRESHOLD
        except Exception:
            return False

    async def _score_voice_only(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> Dict[str, Any]:
        """仅做文风评分，用于决定是否先修文。"""
        voice_service = self._get_voice_service()
        if not voice_service or not content or not str(content).strip():
            return {"drift_alert": False, "similarity_score": None}

        try:
            if getattr(voice_service, "use_llm_mode", False):
                return await voice_service.score_chapter_async(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    content=content,
                )
            return voice_service.score_chapter(
                novel_id=novel_id,
                chapter_number=chapter_number,
                content=content,
            )
        except Exception as e:
            logger.warning("[%s] 文风预检失败，跳过自动修文：%s", novel_id, e)
            return {"drift_alert": False, "similarity_score": None}


    def _build_voice_rewrite_variables(
        self,
        novel: Novel,
        chapter,
        content: str,
        similarity_score: float,
        attempt: int,
    ) -> Dict[str, Any]:
        """构建定向修正文风的变量快照。"""
        style_summary = ""
        voice_anchors = ""
        voice_service = self._get_voice_service()
        try:
            fingerprint_repo = getattr(voice_service, "fingerprint_repo", None)
            if fingerprint_repo:
                fingerprint = fingerprint_repo.get_by_novel(novel.novel_id.value, None)
                style_summary = build_style_summary(fingerprint)
        except Exception as e:
            logger.debug("[%s] style_summary 获取失败: %s", novel.novel_id, e)

        if self.context_builder:
            try:
                voice_anchors = self.context_builder.build_voice_anchor_system_section(
                    novel.novel_id.value
                )
            except Exception as e:
                logger.debug("[%s] voice anchors 获取失败: %s", novel.novel_id, e)

        style_block = style_summary.strip() or "暂无明确统计摘要，优先保持既有作者语气与句式节奏。"
        anchor_block = voice_anchors.strip() or "无额外角色声线锚点。"
        outline = (getattr(chapter, "outline", "") or "").strip() or "无单独大纲，必须严格保留现有剧情事实。"

        return {
            "style_fingerprint": style_block,
            "anchor_block": anchor_block,
            "chapter_number": str(chapter.number),
            "attempt": str(attempt),
            "similarity_score": f"{similarity_score:.4f}",
            "threshold": f"{VOICE_REWRITE_THRESHOLD:.2f}",
            "outline": outline,
            "content": content,
        }

    def _build_voice_rewrite_prompt(
        self,
        novel: Novel,
        chapter,
        content: str,
        similarity_score: float,
        attempt: int,
    ) -> Prompt:
        """构建定向修正文风的改写提示。"""
        from infrastructure.ai.prompt_keys import VOICE_REWRITE
        from infrastructure.ai.prompt_utils import render_required_prompt

        return render_required_prompt(
            VOICE_REWRITE,
            self._build_voice_rewrite_variables(novel, chapter, content, similarity_score, attempt),
        )

    async def _rewrite_chapter_for_voice(
        self,
        novel: Novel,
        chapter,
        content: str,
        similarity_score: float,
        attempt: int,
    ) -> Optional[str]:
        """执行一次定向修文。"""
        if not self.llm_service:
            return None

        variables = self._build_voice_rewrite_variables(
            novel,
            chapter,
            content,
            similarity_score,
            attempt,
        )
        config = GenerationConfig(
            max_tokens=max(4096, min(8192, int(len(content) * 1.5))),
            temperature=0.35,
        )
        try:
            from application.ai_invocation.autopilot.factory import get_or_create_autopilot_helper_invoker
            from application.ai_invocation.autopilot.helper_invoker import AutopilotHelperRequest
            from infrastructure.ai.prompt_keys import VOICE_REWRITE

            ensure_trace(novel_id=str(novel.novel_id), stage="pipeline.chapter.voice", stage_label="文风修文")
            rewritten_text = await get_or_create_autopilot_helper_invoker(self).invoke_text(
                AutopilotHelperRequest(
                    novel_id=str(getattr(novel.novel_id, "value", novel.novel_id)),
                    stage="audit",
                    operation="autopilot.voice.rewrite",
                    node_key=VOICE_REWRITE,
                    explicit_variables={
                        "style_fingerprint": variables["style_fingerprint"],
                        "anchor_block": variables["anchor_block"],
                        "chapter_number": variables["chapter_number"],
                        "attempt": variables["attempt"],
                        "similarity_score": variables["similarity_score"],
                        "threshold": variables["threshold"],
                        "outline": variables["outline"],
                        "content": variables["content"],
                    },
                    context={
                        "novel_id": str(getattr(novel.novel_id, "value", novel.novel_id)),
                        "chapter_number": getattr(chapter, "number", 0),
                    },
                    metadata={"source": "daemon_host.voice_rewrite"},
                    config={"max_tokens": config.max_tokens, "temperature": config.temperature},
                )
            )
        except Exception as e:
            logger.warning("[%s] 文风定向修文失败（attempt=%d）：%s", novel.novel_id, attempt, e)
            return None

        rewritten = strip_reasoning_artifacts((rewritten_text or "").strip())
        if not rewritten:
            return None
        return rewritten

    async def _apply_voice_rewrite_loop(
        self,
        novel: Novel,
        chapter,
        content: str,
        initial_drift_result: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        """严重漂移时做有限次定向修文，并即时复评分。"""
        current_content = content
        current_result = initial_drift_result or {"drift_alert": False, "similarity_score": None}

        for attempt in range(1, VOICE_REWRITE_MAX_ATTEMPTS + 1):
            if not self._should_attempt_voice_rewrite(current_result):
                break
            if not self._is_still_running(novel):
                logger.info("[%s] 用户已停止，终止文风修文", novel.novel_id)
                break

            similarity = current_result.get("similarity_score")
            logger.warning(
                "[%s] 章节 %s 文风偏离严重（similarity=%s），开始第 %d/%d 次定向修文",
                novel.novel_id,
                chapter.number,
                similarity,
                attempt,
                VOICE_REWRITE_MAX_ATTEMPTS,
            )
            rewritten = await self._rewrite_chapter_for_voice(
                novel,
                chapter,
                current_content,
                float(similarity),
                attempt,
            )
            if not rewritten or rewritten.strip() == current_content.strip():
                logger.warning("[%s] 定向修文未产生有效变化，停止继续重试", novel.novel_id)
                break

            current_content = rewritten
            # 🔥 核心修复：使用独立短连接写入，避免持有长连接写锁阻塞 API 进程
            self._save_chapter_ephemeral(
                novel.novel_id.value, chapter.number,
                content=current_content,
                word_count=len(current_content.strip()),
            )
            current_result = await self._score_voice_only(
                novel.novel_id.value,
                chapter.number,
                current_content,
            )
            logger.info(
                "[%s] 第 %d 次定向修文后相似度=%s drift_alert=%s",
                novel.novel_id,
                attempt,
                current_result.get("similarity_score"),
                current_result.get("drift_alert"),
            )

        return current_content, current_result


    def _legacy_auditing_tasks_and_voice(
        self,
        novel: Novel,
        chapter_num: int,
        content: str,
        chapter_id: ChapterId,
    ) -> Dict[str, Any]:
        """无统一管线时：VOICE + extract_bundle（单次 LLM 叙事/三元组/伏笔）入队 + 同步文风（可能与队列内 VOICE 重复）。"""
        for task_type in [TaskType.VOICE_ANALYSIS, TaskType.EXTRACT_BUNDLE]:
            self.background_task_service.submit_task(
                task_type=task_type,
                novel_id=novel.novel_id,
                chapter_id=chapter_id,
                payload={"content": content, "chapter_number": chapter_num},
            )
        if self.voice_drift_service and content:
            try:
                return self.voice_drift_service.score_chapter(
                    novel_id=novel.novel_id.value,
                    chapter_number=chapter_num,
                    content=content,
                )
            except Exception as e:
                logger.warning("文风检测失败（跳过）：%s", e)
        return {"drift_alert": False, "similarity_score": None}


    def _sum_completed_chapter_words(self, novel_id: str) -> int:
        """已完结章节字数合计，用于宏观诊断字数间隔锚点。"""
        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        total = 0
        for c in chapters:
            st = getattr(c.status, "value", c.status)
            if st == "completed":
                total += _coerce_word_count_to_int(getattr(c, "word_count", None))
        return total


    def _get_last_macro_word_anchor(self, novel_id: str) -> int:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
        row = db.fetch_one(
            """
            SELECT total_words_at_run FROM macro_diagnosis_results
            WHERE novel_id=? ORDER BY created_at DESC LIMIT 1
            """,
            (novel_id,),
        )
        if not row:
            return 0
        v = row.get("total_words_at_run")
        return int(v) if v is not None else 0


    def _macro_diagnosis_should_run(self, novel: Novel, completed_count: int) -> tuple:
        """触发：任一卷（Volume）章节范围完结；或累计字数距上次诊断 ≥ 约 6 万字（5~10 万取中）。"""
        from application.audit.services.macro_diagnosis_service import MACRO_DIAGNOSIS_WORD_INTERVAL
        from domain.structure.story_node import NodeType

        novel_id = novel.novel_id.value
        total_words = self._sum_completed_chapter_words(novel_id)

        if self.story_node_repo:
            try:
                nodes = self.story_node_repo.get_by_novel_sync(novel_id)
                for n in nodes:
                    if n.node_type == NodeType.VOLUME and n.chapter_end == completed_count:
                        return True, f"卷「{n.title or n.number}」完结（第{completed_count}章）"
            except Exception as e:
                logger.debug("[%s] 宏观诊断卷检测跳过: %s", novel_id, e)

        last_anchor = self._get_last_macro_word_anchor(novel_id)
        if total_words >= last_anchor + MACRO_DIAGNOSIS_WORD_INTERVAL:
            return True, (
                f"字数间隔（累计约{total_words}字，距上次锚点≥{MACRO_DIAGNOSIS_WORD_INTERVAL // 10000}万字）"
            )
        return False, ""

    async def _auto_trigger_macro_diagnosis(self, novel: Novel, completed_count: int) -> None:
        """自动触发宏观诊断：卷完结或字数间隔；结果仅用于静默 context_patch，不经前端提案。"""
        try:
            should_trigger, trigger_reason = self._macro_diagnosis_should_run(novel, completed_count)
            if not should_trigger:
                return

            total_words = self._sum_completed_chapter_words(novel.novel_id.value)
            logger.info(f"[{novel.novel_id}] 自动触发宏观诊断：{trigger_reason}")

            asyncio.create_task(
                self._run_macro_diagnosis_background(novel.novel_id.value, total_words, trigger_reason)
            )

        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 自动触发宏观诊断失败: {e}")

    async def _run_macro_diagnosis_background(
        self,
        novel_id: str,
        total_words_snapshot: int,
        trigger_reason: str,
    ) -> None:
        """后台执行宏观诊断：扫描结果写入 context_patch，供生成上下文头部静默注入。"""
        try:
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository
            from application.audit.services.macro_refactor_scanner import MacroRefactorScanner
            from application.audit.services.macro_diagnosis_service import MacroDiagnosisService
            
            logger.info(f"[{novel_id}] 宏观诊断后台任务已启动")
            
            db = get_database()
            narrative_event_repo = SqliteNarrativeEventRepository(db)
            scanner = MacroRefactorScanner(narrative_event_repo)
            diagnosis_service = MacroDiagnosisService(db, scanner)
            
            result = diagnosis_service.run_full_diagnosis(
                novel_id=novel_id,
                trigger_reason=trigger_reason,
                traits=None,
                total_words_at_run=total_words_snapshot,
            )
            
            if result.status == "completed":
                logger.info(
                    f"[{novel_id}] ✅ 宏观诊断完成："
                    f"扫描 {result.trait} 人设，发现 {len(result.breakpoints)} 个冲突断点"
                )
            else:
                logger.warning(f"[{novel_id}] 宏观诊断失败：{result.error_message}")

        except Exception as e:
            logger.warning(f"[{novel_id}] 宏观诊断后台任务失败: {e}", exc_info=True)

    async def _score_tension(self, content: str) -> int:
        """Legacy single-axis tension probe.

        Kept only for explicit emergency callers. Formal chapter auditing uses
        the multidimensional aftermath score; this helper must not synthesize a
        neutral score when evaluation fails.
        """
        if not content or len(content) < 200:
            return 0

        snippet = content[:500]  # 只取前 500 字，节省 token

        try:
            from application.ai_invocation.autopilot.factory import get_or_create_autopilot_helper_invoker
            from application.ai_invocation.autopilot.helper_invoker import AutopilotHelperRequest
            from infrastructure.ai.prompt_keys import TENSION_SCORING

            raw = await get_or_create_autopilot_helper_invoker(self).invoke_text(
                AutopilotHelperRequest(
                    novel_id="global",
                    stage="audit",
                    operation="autopilot.tension.score",
                    node_key=TENSION_SCORING,
                    explicit_variables={"content": snippet},
                    context={},
                    metadata={"source": "daemon_host.tension_score"},
                    config={"max_tokens": 5, "temperature": 0.1},
                )
            )
        except Exception:
            return 0
        digits = "".join(filter(str.isdigit, str(raw)[:3]))
        if not digits:
            return 5
        score = int(digits)
        return max(1, min(10, score))

    async def _stream_llm_with_stop_watch(
        self,
        prompt: Prompt,
        config: GenerationConfig,
        novel=None,
        chapter_draft_so_far: str = "",
        total_timeout: float = 600.0,
        idle_timeout: float = 120.0,
    ) -> str:
        """与 workflow 共用同一套 Prompt + LLM；novel 传入时并行轮询 DB 是否已停止。

        优化点：
        1. 快速响应停止信号（0.3s 轮询间隔）
        2. 批量推送 chunks，减少跨进程通信开销
        3. 使用共享状态缓存，减少 DB 访问
        4. 超时保护：总时间上限 + 空闲超时（防止 LLM 挂起）

        Args:
            prompt: LLM 提示词
            config: 生成配置
            novel: 小说对象
            total_timeout: 总时间上限（秒），默认 10 分钟
            idle_timeout: 空闲超时（秒），默认 2 分钟无数据则终止
        """
        if novel is not None:
            try:
                return await self._stream_llm_via_autopilot_invocation(
                    prompt,
                    config,
                    novel=novel,
                    chapter_draft_so_far=chapter_draft_so_far,
                )
            except RuntimeError as exc:
                logger.error(
                    "[%s] AI Invocation 写作通道不可用，停止自动驾驶直连回退: %s",
                    getattr(novel, "novel_id", "unknown"),
                    exc,
                )
                raise

        content = ""
        stop_detected = asyncio.Event()
        watch_task = None
        idle_watch_task = None
        nid = getattr(novel.novel_id, "value", novel.novel_id) if novel else None

        # 批量推送缓冲（当前节拍内的 LLM 增量）
        chunk_buffer: List[str] = []
        last_push_time = time.time()
        last_chunk_time = time.time()  # 追踪最后一次收到数据的时间
        # 🔥 高频推送整章累积快照，避免前端对多节拍增量做 += 时出现衔接重复/乱序
        CHUNK_PUSH_INTERVAL = 0.15
        start_time = time.time()

        def _live_chapter_snapshot() -> str:
            prior = (chapter_draft_so_far or "").rstrip()
            beat_part = "".join(chunk_buffer)
            if not prior:
                return beat_part
            if not beat_part:
                return prior
            return f"{prior}\n\n{beat_part}"

        async def _watch_stop_signal() -> None:
            """停止信号监听（三通道，快速响应）。

            优先级：
            1. threading.Event.is_set() → 亚微秒级，零 I/O
            2. mp.Queue 主动消费 → 毫秒级，设置 threading.Event
            3. DB 降级 → 每 10 秒检查一次（🔥 之前每 50ms 查 DB = 每秒 20 次 SQLite 连接，
               虽然在守护进程独立进程中不直接阻塞 API，但会加剧 SQLite 锁竞争，
               间接导致 API 进程的 DB 查询更频繁地超时）
            """
            db_check_counter = 0
            DB_CHECK_INTERVAL = 200  # 每 200 次循环（约 10 秒）查一次 DB

            while not stop_detected.is_set():
                await asyncio.sleep(0.05)  # 50ms 检查间隔

                # 通道 1：本地 threading.Event（亚微秒级）
                try:
                    from application.engine.services.novel_stop_signal import is_novel_stopped
                    if is_novel_stopped(novel_id_ref.value):
                        logger.info(f"[{nid}] IPC 停止信号已触发，结束流式")
                        stop_detected.set()
                        return
                except Exception:
                    pass

                # 通道 2：主动消费 mp.Queue（确保停止消息被及时处理）
                try:
                    from application.engine.services.streaming_bus import streaming_bus
                    streaming_bus.consume_control_signals(novel_id_ref.value)
                except Exception:
                    pass

                # 🔥 消费后下一轮循环的通道 1 会立即检查，无需重复

                # 通道 3：DB 降级（🔥 降频：每 ~10 秒检查一次，不再每 50ms）
                db_check_counter += 1
                if db_check_counter >= DB_CHECK_INTERVAL:
                    db_check_counter = 0
                    if not self._novel_is_running_in_db(novel_id_ref):
                        logger.info(f"[{nid}] DB 降级检测：已停止，结束流式")
                        stop_detected.set()
                        return

        async def _watch_idle_timeout() -> None:
            """空闲超时检测：长时间无数据则终止"""
            while not stop_detected.is_set():
                await asyncio.sleep(5.0)  # 每 5 秒检查一次
                elapsed_since_chunk = time.time() - last_chunk_time
                if elapsed_since_chunk >= idle_timeout:
                    logger.warning(
                        f"[{nid}] ⚠️ 流式生成空闲超时（{idle_timeout}s 无数据），强制终止"
                    )
                    stop_detected.set()
                    return

                # 检查总时间
                total_elapsed = time.time() - start_time
                if total_elapsed >= total_timeout:
                    logger.warning(
                        f"[{nid}] ⚠️ 流式生成总时间超限（{total_timeout}s），强制终止"
                    )
                    stop_detected.set()
                    return

        if novel is not None:
            novel_id_ref = novel.novel_id
            watch_task = asyncio.create_task(_watch_stop_signal())

        # 启动空闲超时检测
        idle_watch_task = asyncio.create_task(_watch_idle_timeout())

        try:
            async for chunk in self.llm_service.stream_generate(prompt, config):
                if stop_detected.is_set():
                    break
                content += chunk
                last_chunk_time = time.time()  # 更新最后收到数据的时间

                # 🔧 优化：高频小批量推送，实现流式打字机效果
                if novel is not None and chunk:
                    chunk_buffer.append(chunk)
                    current_time = time.time()
                    # 定期推送整章快照（含已完成节拍 + 当前节拍流式部分）
                    if current_time - last_push_time >= CHUNK_PUSH_INTERVAL:
                        await self._push_streaming_chunk(
                            novel.novel_id.value,
                            content=_live_chapter_snapshot(),
                        )
                        last_push_time = current_time

                if stop_detected.is_set():
                    break
        except asyncio.CancelledError:
            logger.info(f"[{nid}] 流式生成被取消")
            raise
        except Exception as e:
            logger.error(f"[{nid}] 流式生成异常: {e}")
            raise
        finally:
            # 🔧 确保推送最后一帧整章快照
            if novel is not None and chunk_buffer:
                await self._push_streaming_chunk(
                    novel.novel_id.value,
                    content=_live_chapter_snapshot(),
                )

            stop_detected.set()
            if watch_task is not None:
                watch_task.cancel()
                try:
                    await watch_task
                except asyncio.CancelledError:
                    pass
            if idle_watch_task is not None:
                idle_watch_task.cancel()
                try:
                    await idle_watch_task
                except asyncio.CancelledError:
                    pass

        if novel is not None:
            self._merge_autopilot_status_from_db(novel)

        return strip_reasoning_artifacts(content)

    async def _stream_llm_via_autopilot_invocation(
        self,
        prompt: Prompt,
        config: GenerationConfig,
        *,
        novel,
        chapter_draft_so_far: str = "",
    ) -> str:
        """Run autopilot prose generation through AI Invocation.

        This preserves the existing streaming UI by pushing accumulated snapshots
        while the attempt is running, but session/spec/variables/prompt/attempt/
        adoption/commit all go through the unified control plane.
        """
        try:
            from application.ai_invocation.autopilot.factory import get_or_create_autopilot_orchestrator
            from application.ai_invocation.autopilot.intents import AutopilotInvocationIntent
            from application.ai_invocation.autopilot.policy import AutopilotInvocationPolicyResolver
            from application.ai_invocation.contracts import ensure_invocation_contract
            from application.ai_invocation.dtos import InvocationPolicy, InvocationSessionStatus
            from application.ai_invocation.variable_hub import VariableWrite
            from infrastructure.ai.prompt_keys import AUTOPILOT_STREAM_BEAT
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository
        except Exception as exc:
            logger.debug("autopilot invocation imports unavailable: %s", exc)
            raise RuntimeError("autopilot_invocation_unavailable") from exc

        novel_id = getattr(novel.novel_id, "value", novel.novel_id)
        chapter_number = int(getattr(novel, "current_chapter_number", 0) or 0)
        if chapter_number <= 0:
            chapter_number = int(getattr(novel, "current_auto_chapters", 0) or 0) + 1
        beat_index = int(getattr(novel, "current_beat_index", 0) or 0)
        context_key = f"novel_id:{novel_id}|chapter_number:{chapter_number}|beat_index:{beat_index}"

        db = get_database()
        ensure_invocation_contract("autopilot.prose.from_script", AUTOPILOT_STREAM_BEAT, db)
        variable_repo = SqliteVariableHubRepository(db)
        outline = ""
        user_prompt = getattr(prompt, "user", "") or ""
        for line in user_prompt.splitlines():
            if line.strip():
                outline = line.strip()
                break
        target_words = max(1, int((config.max_tokens or 1000) / 1.3))
        variables = {
            "outline": outline or user_prompt[:500],
            "last_paragraph": format_prior_draft_for_prompt(chapter_draft_so_far)[-800:],
            "beat_goal": user_prompt,
            "target_words": target_words,
            "context_block": user_prompt,
        }
        for key, value in (
            ("chapter.outline", variables["outline"]),
            ("chapter.draft_so_far", variables["last_paragraph"]),
            ("beat.current", variables["beat_goal"]),
            ("beat.target_words", variables["target_words"]),
            ("materialized.beat.prompt_context", variables["context_block"]),
        ):
            variable_repo.set_value(
                VariableWrite(
                    key=key,
                    value=value,
                    context_key=context_key,
                    source_node_key=AUTOPILOT_STREAM_BEAT,
                    source_trace_id=AUTOPILOT_STREAM_BEAT,
                    scope="beat" if key.startswith("beat.") or key.startswith("materialized.beat.") else "chapter",
                    stage="writing",
                    display_name=key,
                    value_type="integer" if key == "beat.target_words" else "string",
                )
            )

        policy = AutopilotInvocationPolicyResolver().resolve(
            operation="autopilot.prose.from_script",
            node_key=AUTOPILOT_STREAM_BEAT,
            novel=novel,
            context={"novel_id": novel_id, "chapter_number": chapter_number, "beat_index": beat_index},
        )
        # StoryPipeline/legacy streaming cannot wait for manual review mid-token
        # unless the user explicitly disables auto approve. In interactive mode,
        # prepare() pauses and the caller will surface an empty result.
        intent = AutopilotInvocationIntent(
            novel_id=str(novel_id),
            stage="writing",
            operation="autopilot.prose.from_script",
            node_key=AUTOPILOT_STREAM_BEAT,
            context={"novel_id": novel_id, "chapter_number": chapter_number, "beat_index": beat_index},
            explicit_variables=variables,
            continuation_handler_key="autopilot_prose_generation",
            policy_hint=policy,
            metadata={"source": "daemon_host.stream_llm", "context_key": context_key},
        )
        orchestrator = get_or_create_autopilot_orchestrator(self)
        prepared = await orchestrator.prepare(intent)
        if prepared.session.status in {
            InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW,
            InvocationSessionStatus.BLOCKED,
        }:
            self._update_shared_state(
                str(novel_id),
                active_invocation_session_id=prepared.session.id,
                active_invocation_operation=prepared.session.operation,
                active_invocation_node_key=prepared.session.node_key,
                active_invocation_status=prepared.session.status.value,
                active_invocation_policy=prepared.session.policy.value,
                requires_ai_review=True,
                autopilot_pause_reason="awaiting_ai_review",
            )
            novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
            novel.autopilot_status = AutopilotStatus.RUNNING
            self._flush_novel(novel)
            return ""

        chunk_buffer: list[str] = []
        last_push_time = time.time()

        def _live_snapshot() -> str:
            prior = (chapter_draft_so_far or "").rstrip()
            beat_part = "".join(chunk_buffer)
            if not prior:
                return beat_part
            if not beat_part:
                return prior
            return f"{prior}\n\n{beat_part}"

        async def _push_snapshot() -> None:
            snap = _live_snapshot()
            if snap:
                await self._push_streaming_chunk(str(novel_id), content=snap)

        def _on_chunk(chunk: str, _content: str):
            nonlocal last_push_time
            if not self._is_still_running(novel):
                return False
            chunk_buffer.append(chunk)
            now = time.time()
            if now - last_push_time >= 0.15:
                try:
                    from application.engine.services.streaming_bus import streaming_bus

                    streaming_bus.publish(str(novel_id), "", content=_live_snapshot())
                    self._write_daemon_heartbeat()
                except Exception:
                    pass
                last_push_time = now
            return True

        outcome = await orchestrator.generate_prepared_streaming(
            intent=intent,
            prepared_result=prepared,
            config=config,
            on_chunk=_on_chunk,
        )
        await _push_snapshot()
        return strip_reasoning_artifacts(outcome.accepted_content or "".join(chunk_buffer))

    async def _push_streaming_chunk(
        self,
        novel_id: str,
        chunk: str = "",
        *,
        content: Optional[str] = None,
    ):
        """推送流式正文到全局队列，供 SSE 接口消费。

        ``content`` 为整章累积快照（编辑区应直接替换）；``chunk`` 为旧版增量片段。
        """
        from application.engine.services.streaming_bus import streaming_bus
        streaming_bus.publish(novel_id, chunk, content=content)
        # 🔥 流式生成期间更新心跳，避免前端误判"后端无响应"
        self._write_daemon_heartbeat()


    def _update_stream_metadata(self, novel_id: str, beat_index: int, word_count: int):
        """更新流式元数据（供外部调用）"""
        from application.engine.services.streaming_bus import streaming_bus
        streaming_bus.update_beat(novel_id, beat_index, word_count)

    async def _stream_one_beat(
        self,
        outline,
        context,
        beat_prompt,
        beat,
        novel=None,
        voice_anchors: str = "",
        chapter_draft_so_far: str = "",
    ) -> str:
        """无 AutoNovelGenerationWorkflow 时的兼容写作路径。

        提示词仍必须来自 CPMS；缺失时直接阻塞，禁止回退到隐藏硬编码提示词。
        """
        from infrastructure.ai.prompt_keys import WORKFLOW_CHAPTER_GENERATION
        from infrastructure.ai.prompt_utils import render_required_prompt

        va = (voice_anchors or "").strip()
        voice_block = ""
        if va:
            voice_block = (
                "【角色声线与肢体语言（Bible 锚点，必须遵守）】\n"
                f"{va}\n\n"
            )

        context_parts = []
        if context:
            context_parts.append(str(context))
        prior = format_prior_draft_for_prompt(chapter_draft_so_far)
        prior_draft = ""
        if prior:
            prior_draft = (
                "\n【本章上文（近期全文精确衔接 + 远期回溯避免重复；禁止复述或重复已写对白与情节）】\n"
                f"{prior}"
            )
            # V2：节拍间衔接锚点注入
            try:
                from application.workflows.beat_continuation import (
                    extract_beat_tail_anchor,
                    build_beat_transition_directive,
                )
                anchor = extract_beat_tail_anchor(prior)
                if anchor.tail_state or anchor.last_moment:
                    next_desc = (beat_prompt or "").strip()[:80] if beat_prompt else ""
                    directive = build_beat_transition_directive(
                        anchor, getattr(beat, 'index', 0) or 0, 1, next_desc,
                    )
                    prior_draft += f"\n{directive}"
            except Exception:
                pass  # 降级：无锚点则不加

        # 输出 token 策略与整章生成一致：统一走全局输出下限，不随目标字数动态变化。
        from engine.runtime.generation_token_policy import CHAPTER_PROSE_MAX_TOKENS

        max_tokens = CHAPTER_PROSE_MAX_TOKENS
        target_words = int(getattr(beat, "target_words", 0) or max_tokens)

        prompt = render_required_prompt(
            WORKFLOW_CHAPTER_GENERATION,
            {
                "planning_section": "",
                "voice_block": voice_block,
                "behavior_protocol": "",
                "character_state_lock": "",
                "context": "\n\n".join(context_parts),
                "fact_lock": "",
                "length_rule": f"7. 本节目标约 {target_words} 字，严格按当前节拍聚焦点写作。",
                "beat_extra": "",
                "outline": str(outline or ""),
                "prior_draft": prior_draft,
                "beat_section": (beat_prompt or "").strip(),
            },
        )
        config = GenerationConfig(max_tokens=max_tokens, temperature=0.85)
        return await self._stream_llm_with_stop_watch(
            prompt, config, novel=novel, chapter_draft_so_far=chapter_draft_so_far
        )

    async def _upsert_chapter_content(self, novel, chapter_node, content: str, status: str):
        """最小事务：只更新章节内容，不涉及其他表

        🔥 CQRS 优化：draft 状态通过持久化队列写入，避免多进程锁竞争。
        但 completed 状态是关键状态转换，必须直接写 DB 确保立即可见，
        否则后续逻辑（如 _find_next_unwritten_chapter_async）会因持久化队列
        延迟而读到旧 draft 状态，导致重复审计同一章节。

        安全规则：
        1. 空内容不能将状态更新为 completed（防止空章节被标记为完成）
        2. 空内容不会覆盖已有内容（防止意外清空）
        """
        from domain.novel.entities.chapter import Chapter, ChapterStatus
        from domain.novel.value_objects.novel_id import NovelId
        from application.engine.services.persistence_queue import PersistenceCommandType

        stripped = (content or "").strip()
        try:
            if getattr(novel, "generation_prefs", None) is not None and getattr(
                novel.generation_prefs, "inline_prose_aggregation_enabled", False
            ):
                content_str = aggregate_inline_prose_fragments(stripped)
            else:
                content_str = stripped
        except Exception:
            content_str = stripped
        novel_id = novel.novel_id.value
        chapter_number = chapter_node.number

        # 🔥 关键修复：completed 状态必须直接写 DB
        # 之前全部走持久化队列，如果队列消费延迟，_find_next_unwritten_chapter_async
        # 会读到旧 draft 状态，导致审计完成→写文→跳过→再审计的死循环
        is_critical_status = status == "completed"

        if not is_critical_status:
            # draft 状态：优先使用持久化队列（无锁竞争）
            payload = {
                "novel_id": novel_id,
                "chapter_number": chapter_number,
                "content": content_str,
                "status": status if content_str else "draft",
            }

            if self._push_persistence_command(PersistenceCommandType.UPSERT_CHAPTER.value, payload):
                logger.debug(f"[{novel_id}] 章节内容已推送到持久化队列: ch={chapter_number}")
                return

        # 🔥 completed 状态或持久化队列不可用：用独立短连接写 DB
        # 替代原来的 chapter_repository.save()（长连接持有写锁阻塞 API 进程）
        existing = self.chapter_repository.get_by_novel_and_number(
            NovelId(novel_id), chapter_number
        )
        if existing:
            existing_content = (existing.content or "").strip()

            # 安全检查：空内容不能标记为 completed
            if not content_str and status == "completed":
                logger.warning(
                    f"[{novel_id}] 拒绝将章节 {chapter_number} 标记为 completed：内容为空"
                )
                return

            # 防御：避免意外用空串覆盖已有正文
            if not content_str:
                if status == "draft" and existing_content:
                    logger.debug(
                        f"[{novel_id}] 章节 {chapter_number} 内容为空，仅更新状态为 draft（保留已有内容）"
                    )
                    self._save_chapter_ephemeral(novel_id, chapter_number, status="draft")
                return

            # 正常更新：使用独立短连接
            import uuid
            wc = len(content_str)
            ok = self._save_chapter_ephemeral(
                novel_id, chapter_number,
                content=content_str,
                status=status,
                word_count=wc,
            )
            if ok:
                logger.debug(f"[{novel_id}] 章节已通过短连接落盘: ch={chapter_number} status={status}")
            else:
                logger.warning(f"[{novel_id}] 短连接写入失败，已降级到持久化队列: ch={chapter_number}")
        else:
            # 新建章节：需要 INSERT，用短连接
            if not content_str and status == "completed":
                logger.warning(
                    f"[{novel_id}] 拒绝创建空的 completed 章节 {chapter_number}"
                )
                return

            import uuid
            ch_id = chapter_node.id or str(uuid.uuid4())
            ch_title = chapter_node.title or ""
            ch_outline = chapter_node.outline or ""
            ch_status = status if content_str else "draft"
            wc = len(content_str)

            sql = """INSERT INTO chapters (id, novel_id, number, title, content, outline, status, word_count,
                                             tension_score, plot_tension, emotional_tension, pacing_tension,
                                             created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
            # 🔥 CQRS：推队列，由 API 进程消费者串行执行（零锁竞争）
            self._queue_sql(
                sql, [ch_id, novel_id, chapter_number, ch_title, content_str, ch_outline, ch_status, wc]
            )


    def _find_parent_volume_for_new_act(
        self,
        volume_nodes: list,
        act_nodes: list,
        current_auto_chapters: int,
        target_chapters: int,
        rec_acts_per_volume: int,
        novel_id: str,
    ):
        """智能选择新幕的父卷。

        核心改进（替代原来的线性均分算法）：
        1. 统计每个已有卷下已挂载了多少幕
        2. 优先选择「当前写入卷」（幕数尚未达到 rec_acts_per_volume 的卷）
        3. 只有当前卷的幕数已经满了，才跳到下一卷
        4. 这样确保每卷都能写够足够多的幕，而不是写3幕就跑路
        """
        if not volume_nodes:
            logger.warning(f"[{novel_id}] 无可用卷节点，无法确定父卷")
            return None

        # 统计每个卷下的幕数量
        volume_act_counts: Dict[int, int] = {}
        for v in volume_nodes:
            volume_act_counts[v.number] = sum(
                1 for a in act_nodes if a.parent_id == v.id
            )

        # 策略：从第一个卷开始找，返回第一个「幕数 < rec_acts_per_volume」的卷
        # 如果所有卷都满了，返回最后一个卷（允许超发）
        for v in volume_nodes:
            current_count = volume_act_counts.get(v.number, 0)
            if current_count < rec_acts_per_volume:
                logger.info(
                    f"[{novel_id}] 父卷选择：第{v}卷已有{current_count}幕"
                    f"（上限{rec_acts_per_volume}），继续在本卷创建新幕"
                )
                return v

        # 所有卷都已达到建议幕数，挂在最后一个卷上（允许超发）
        last_volume = volume_nodes[-1]
        logger.info(
            f"[{novel_id}] 父卷选择：所有卷已达{rec_acts_per_volume}幕上限"
            f"，新幕挂到最后一个卷（第{last_volume.number}卷）"
        )
        return last_volume

    async def _find_next_unwritten_chapter_async(self, novel):
        """找到下一个未写的章节节点

        🔥 修复：增加已审计章节的跳过逻辑。
        当持久化队列延迟导致章节在 DB 中仍为 draft 时，
        通过 last_audit_chapter_number 判断该章节已经审计完成，
        避免重复生成同一章节。
        """
        novel_id = novel.novel_id.value
        all_nodes = await self.story_node_repo.get_by_novel(novel_id)
        chapter_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "chapter"],
            key=lambda n: n.number
        )

        last_audited_num = getattr(novel, 'last_audit_chapter_number', None)

        for node in chapter_nodes:
            # 🔥 跳过已审计的章节（即使 DB 中仍为 draft，也视为已完成）
            if last_audited_num is not None and node.number <= last_audited_num:
                # 确保已审计但 DB 仍为 draft 的章节被强制标记为 completed
                chapter = self.chapter_repository.get_by_novel_and_number(
                    NovelId(novel_id), node.number
                )
                if chapter and chapter.status.value != "completed":
                    logger.warning(
                        f"[{novel_id}] 章节 {node.number} 已审计但 DB 仍为 {chapter.status.value}，"
                        f"强制修正为 completed"
                    )
                    chapter.status = ChapterStatus.COMPLETED
                    # 🔥 核心修复：使用独立短连接写入 completed 状态
                    self._save_chapter_ephemeral(novel_id, node.number, status="completed")
                continue

            chapter = self.chapter_repository.get_by_novel_and_number(
                NovelId(novel_id), node.number
            )
            if not chapter or chapter.status.value != "completed":
                return node
        return None

    async def _current_act_fully_written(self, novel) -> bool:
        """检查当前幕是否已全部写完"""
        novel_id = novel.novel_id.value
        all_nodes = await self.story_node_repo.get_by_novel(novel_id)
        act_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "act"],
            key=lambda n: n.number
        )

        current_act_node = next(
            (n for n in act_nodes if n.number == novel.current_act + 1),
            None
        )
        if not current_act_node:
            return True

        act_children = self.story_node_repo.get_children_sync(current_act_node.id)
        chapter_nodes = [n for n in act_children if n.node_type.value == "chapter"]
        if not chapter_nodes:
            logger.warning(
                "[%s] 当前第 %s 幕没有章节节点，不能视为已写完；应回到幕级规划",
                novel_id,
                novel.current_act + 1,
            )
            return False

        for node in chapter_nodes:
            chapter = self.chapter_repository.get_by_novel_and_number(
                NovelId(novel_id), node.number
            )
            if not chapter or chapter.status.value != "completed":
                return False
        return True

    async def _get_existing_chapter_content(self, novel, chapter_num) -> Optional[str]:
        """获取已存在的章节内容（用于断点续写）"""
        chapter = self.chapter_repository.get_by_novel_and_number(
            NovelId(novel.novel_id.value), chapter_num
        )
        return chapter.content if chapter else None

    async def _maybe_generate_summaries(self, novel: Novel, completed_count: int) -> None:
        """摘要生成钩子（双轨融合 - 轨道一）
        
        触发时机：
        1. 检查点摘要：每 20 章
        2. 幕摘要：幕完成时
        3. 卷摘要：卷完成时
        4. 部摘要：部完成时
        """
        if not self.volume_summary_service:
            return
        
        try:
            novel_id = novel.novel_id.value
            
            # 1. 检查点摘要（每 20 章）
            if await self.volume_summary_service.should_generate_checkpoint(novel_id, completed_count):
                logger.info(f"[{novel_id}] 生成检查点摘要（第 {completed_count} 章）")
                result = await self.volume_summary_service.generate_checkpoint_summary(novel_id, completed_count)
                if result.success:
                    logger.info(f"[{novel_id}] 检查点摘要生成成功")
                else:
                    logger.warning(f"[{novel_id}] 检查点摘要生成失败: {result.error}")
            
            # 2. 幕摘要（幕完成时）
            all_nodes = await self.story_node_repo.get_by_novel(novel_id)
            act_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "act"],
                key=lambda x: x.number
            )
            
            if act_nodes:
                # 找到最近完成的幕
                for act in reversed(act_nodes):
                    if act.chapter_end and act.chapter_end <= completed_count:
                        # 检查是否已生成摘要
                        has_summary = act.metadata.get("summary") if act.metadata else None
                        if not has_summary:
                            logger.info(f"[{novel_id}] 生成幕摘要: {act.title}")
                            result = await self.volume_summary_service.generate_act_summary(novel_id, act.id)
                            if result.success:
                                logger.info(f"[{novel_id}] 幕摘要生成成功: {act.title}")
                            break
            
            # 3. 卷摘要（检测卷是否完成）
            volume_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "volume"],
                key=lambda x: x.number
            )
            
            for vol in volume_nodes:
                if vol.chapter_end and vol.chapter_end <= completed_count:
                    has_summary = vol.metadata.get("summary") if vol.metadata else None
                    if not has_summary:
                        logger.info(f"[{novel_id}] 生成卷摘要: {vol.title}")
                        result = await self.volume_summary_service.generate_volume_summary(novel_id, vol.number)
                        if result.success:
                            logger.info(f"[{novel_id}] 卷摘要生成成功: {vol.title}")
                        break
            
            # 4. 部摘要（检测部是否完成）
            part_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "part"],
                key=lambda x: x.number
            )
            
            for part in part_nodes:
                # 部完成的判断：最后一个卷已完成
                child_volumes = [v for v in volume_nodes if v.parent_id == part.id]
                if child_volumes:
                    last_vol = max(child_volumes, key=lambda x: x.number)
                    if last_vol.chapter_end and last_vol.chapter_end <= completed_count:
                        has_summary = part.metadata.get("summary") if part.metadata else None
                        if not has_summary:
                            logger.info(f"[{novel_id}] 生成部摘要: {part.title}")
                            result = await self.volume_summary_service.generate_part_summary(novel_id, part.number)
                            if result.success:
                                logger.info(f"[{novel_id}] 部摘要生成成功: {part.title}")
                            break
        
        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 摘要生成失败: {e}")
