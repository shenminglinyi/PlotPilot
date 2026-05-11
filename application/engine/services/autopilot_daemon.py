"""自动驾驶守护进程 v2 - 全托管写作引擎（事务最小化 + 节拍幂等）

核心设计：
1. 死循环轮询数据库，捞出所有 autopilot_status=RUNNING 的小说
2. 根据 current_stage 执行对应的状态机逻辑
3. 事务最小化：DB 写操作只在读状态和更新状态两个瞬间，LLM 请求期间不持有锁
4. 节拍级幂等：每写完一个节拍立刻落库，断点续写从 current_beat_index 恢复
5. 熔断保护：连续失败 3 次挂起单本小说，全局熔断器防止 API 雪崩
"""
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
from domain.novel.entities.chapter import ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.engine.services.context_builder import ContextBuilder
from application.engine.services.background_task_service import BackgroundTaskService, TaskType
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from application.engine.services.style_constraint_builder import build_style_summary
from application.ai.llm_output_sanitize import strip_reasoning_artifacts
from application.ai.llm_retry_policy import LLM_MAX_TOTAL_ATTEMPTS
from application.workflows.beat_continuation import format_prior_draft_for_prompt
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.word_count import WordCount

logger = logging.getLogger(__name__)


def _coerce_word_count_to_int(wc: Any) -> int:
    """章节 word_count 可能为 int 或 WordCount 值对象。"""
    if wc is None:
        return 0
    if isinstance(wc, WordCount):
        return wc.value
    return int(wc)

# 定向修文：单章内 LLM 修文轮数上限（与全局一致）
VOICE_REWRITE_MAX_ATTEMPTS = LLM_MAX_TOTAL_ATTEMPTS
VOICE_REWRITE_THRESHOLD = 0.68
VOICE_WARNING_THRESHOLD_FALLBACK = 0.75


class AutopilotDaemon:
    """自动驾驶守护进程（v2 完整实现）"""

    def __init__(
        self,
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
        chapter_workflow: Optional[AutoNovelGenerationWorkflow] = None,
        aftermath_pipeline: Optional[ChapterAftermathPipeline] = None,
        volume_summary_service=None,
        foreshadowing_repository=None,
        knowledge_service=None,
    ):
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
        self.volume_summary_service = volume_summary_service
        self.foreshadowing_repository = foreshadowing_repository
        self.knowledge_service = knowledge_service

        # 惰性初始化 VolumeSummaryService
        if not self.volume_summary_service and llm_service and story_node_repo:
            from application.blueprint.services.volume_summary_service import VolumeSummaryService
            self.volume_summary_service = VolumeSummaryService(
                llm_service=llm_service,
                story_node_repository=story_node_repo,
                chapter_repository=chapter_repository,
                foreshadowing_repository=foreshadowing_repository,
            )

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

    def run_forever(self):
        """守护进程主循环（事务最小化原则）"""
        logger.info("=" * 80)
        logger.info("🚀 Autopilot Daemon Started")
        logger.info(f"   Poll Interval: {self.poll_interval}s")
        logger.info(f"   Circuit Breaker: {'Enabled' if self.circuit_breaker else 'Disabled'}")
        logger.info(f"   Voice Drift Service: {'Enabled' if self.voice_drift_service else 'Disabled'}")
        logger.info(f"   Volume Summary Service: {'Enabled' if self.volume_summary_service else 'Disabled'}")
        logger.info("=" * 80)

        # 创建持久化事件循环（避免每个小说都 asyncio.run() 创建/销毁循环）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop_count = 0
        while True:
            loop_count += 1
            loop_start = time.time()

            # 🔥 心跳：每轮循环写入共享内存，让前端能判断守护进程是否存活
            # 即使 LLM 调用卡住，心跳仍会定期更新（因为 _call_with_timeout 会超时释放）
            self._write_daemon_heartbeat()

            # 熔断器检查
            if self.circuit_breaker and self.circuit_breaker.is_open():
                wait = self.circuit_breaker.wait_seconds()
                logger.warning(f"⚠️  熔断器打开，暂停 {wait:.0f}s")
                time.sleep(min(wait, self.poll_interval))
                continue

            try:
                # 消费 mp.Queue 中的停止信号消息（设置本地 threading.Event）
                try:
                    from application.engine.services.streaming_bus import streaming_bus
                    streaming_bus.consume_stop_signals()
                except Exception:
                    pass

                active_novels = self._get_active_novels()  # 快速只读查询

                # 🔥 关键修复：清理已恢复为 RUNNING 但本地停止信号仍残留的小说
                # 场景：用户点"停止"→ threading.Event.set() → 用户点"开始"→ DB 改回 RUNNING
                # 但 mp.Queue 的 start_signal 可能还没被消费，threading.Event 仍为 set
                # 导致 _is_still_running() 永远返回 False，小说无法继续处理
                if active_novels:
                    self._cleanup_stale_stop_signals(active_novels)

                if loop_count % 10 == 1:  # 每10轮（约50秒）记录一次状态
                    logger.info(f"🔄 Loop #{loop_count}: 发现 {len(active_novels)} 本活跃小说")

                if active_novels:
                    for novel in active_novels:
                        novel_start = time.time()
                        loop.run_until_complete(self._process_novel(novel))
                        novel_elapsed = time.time() - novel_start
                        logger.debug(f"   [{novel.novel_id}] 处理耗时: {novel_elapsed:.2f}s")

            except Exception as e:
                logger.error(f"❌ Daemon 顶层异常: {e}", exc_info=True)

            loop_elapsed = time.time() - loop_start
            if loop_elapsed > self.poll_interval * 2:
                logger.warning(f"⏱️  Loop #{loop_count} 耗时过长: {loop_elapsed:.2f}s")

            time.sleep(self.poll_interval)

    def _get_active_novels(self) -> List[Novel]:
        """获取所有活跃小说（快速只读）"""
        return self.novel_repository.find_by_autopilot_status(AutopilotStatus.RUNNING.value)

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
        # 降级：通过主进程模块
        try:
            from interfaces.main import update_shared_novel_state
            # 用特殊 key 写入心跳（非小说级别，而是全局级别）
            from interfaces.main import _get_shared_state
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
    ) -> None:
        """🛡️ Anti-AI 审计管线：对生成的章节进行 AI 味检测与审计。

        执行流程：
        1. 使用 ClicheScanner 扫描 AI 味模式
        2. 使用 AntiAIAuditor 生成审计报告
        3. 使用 AntiAIMetricsService 计算指标快照
        4. 使用 AntiAILearningService 学习新模式
        5. 将审计结果持久化到日志

        此方法为异步包装，实际扫描为同步操作。
        不影响主流程，失败仅记录日志。
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

        except Exception as e:
            logger.warning(f"[{novel_id}] Anti-AI 审计失败（不影响主流程）ch={chapter_number}: {e}")

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

            # 衔接度低于 0.6，自动修整
            if result.score < 0.6 and result.issues:
                logger.warning(
                    f"[{novel_id}] 🔗 衔接度低 ({result.score:.2f})，自动修整首段 ch={chapter_number}"
                )
                fixed_content = await svc.auto_fix_opening(
                    novel_id, chapter_number, content, prev_bridge, result, max_rounds=2
                )
                if fixed_content != content:
                    logger.info(
                        f"[{novel_id}] 🔗 首段修整完成 ch={chapter_number} "
                        f"原={len(content)}字→新={len(fixed_content)}字"
                    )
                    return fixed_content
                else:
                    logger.info(f"[{novel_id}] 🔗 首段修整未改变内容 ch={chapter_number}")
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

    async def _process_novel(self, novel: Novel):
        """处理单个小说（全流程）"""
        try:
            # 🔥 二次防线：处理小说前再次清理残留停止信号
            # 场景：_cleanup_stale_stop_signals 和此处之间可能有新的 stop→start 事件
            try:
                from application.engine.services.novel_stop_signal import is_novel_stopped, clear_local_novel_stop
                if is_novel_stopped(novel.novel_id.value):
                    db_status = self._read_autopilot_status_ephemeral(novel.novel_id)
                    if db_status == AutopilotStatus.RUNNING:
                        clear_local_novel_stop(novel.novel_id.value)
                        logger.info(
                            f"[{novel.novel_id}] 🔧 _process_novel: 清除残留停止信号"
                        )
            except Exception:
                pass

            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 用户已停止自动驾驶，跳过本轮")
                return

            stage_name = novel.current_stage.value
            logger.debug(f"[{novel.novel_id}] 当前阶段: {stage_name}")

            if novel.current_stage == NovelStage.MACRO_PLANNING:
                logger.info(f"[{novel.novel_id}] 📋 开始宏观规划")
                await self._handle_macro_planning(novel)
            elif novel.current_stage == NovelStage.ACT_PLANNING:
                logger.info(f"[{novel.novel_id}] 📝 开始幕级规划 (第 {novel.current_act + 1} 幕)")
                await self._handle_act_planning(novel)
            elif novel.current_stage == NovelStage.WRITING:
                logger.info(f"[{novel.novel_id}] ✍️  开始写作 (第 {novel.current_act + 1} 幕)")
                await self._handle_writing(novel)
            elif novel.current_stage == NovelStage.AUDITING:
                logger.info(f"[{novel.novel_id}] 🔍 开始审计")
                await self._handle_auditing(novel)
            elif novel.current_stage == NovelStage.PAUSED_FOR_REVIEW:
                # 全自动模式：跳过审阅，直接进入下一阶段
                if getattr(novel, 'auto_approve_mode', False):
                    logger.info(f"[{novel.novel_id}] 🚀 全自动模式：跳过人工审阅")
                    # 根据当前状态自动进入下一阶段
                    # 宏观规划完成后 -> 幕级规划
                    # 幕级规划完成后 -> 写作
                    # 写作完成后 -> 审计
                    novel.current_stage = NovelStage.ACT_PLANNING
                    self._save_novel_state(novel)
                    return
                else:
                    logger.debug(f"[{novel.novel_id}] ⏸️  等待人工审阅")
                    return  # 人工干预点：不处理，等前端确认

            # ✅ 收尾写库（合并 DB 停止标志，避免把用户「停止」写回 RUNNING）
            self._merge_autopilot_status_from_db(novel)
            if novel.autopilot_status == AutopilotStatus.RUNNING:
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
                novel.consecutive_error_count = 0
            else:
                logger.info(f"[{novel.novel_id}] 💾 本轮结束（用户已停止，不再计成功/重置熔断）")
            self._save_novel_state(novel)
            logger.debug(f"[{novel.novel_id}] 💾 状态已保存")

        except Exception as e:
            logger.error(f"❌ [{novel.novel_id}] 处理失败: {e}", exc_info=True)

            self._merge_autopilot_status_from_db(novel)
            if novel.autopilot_status != AutopilotStatus.RUNNING:
                logger.info(f"[{novel.novel_id}] 处理异常但用户已停止，不累计熔断/失败次数")
                self._save_novel_state(novel)
                return

            # 熔断器：记录失败
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            novel.consecutive_error_count = (novel.consecutive_error_count or 0) + 1

            if novel.consecutive_error_count >= 3:
                # 单本小说连续 3 次错误 → 挂起（不影响其他小说）
                logger.error(f"🚨 [{novel.novel_id}] 连续失败 {novel.consecutive_error_count} 次，挂起等待急救")
                novel.autopilot_status = AutopilotStatus.ERROR
            else:
                logger.warning(f"⚠️  [{novel.novel_id}] 连续失败 {novel.consecutive_error_count}/3 次")
            self._save_novel_state(novel)

    async def _handle_macro_planning(self, novel: Novel):
        """处理宏观规划（规划部/卷/幕）- 使用极速模式让 AI 自主推断结构"""
        if not self._is_still_running(novel):
            return

        # ★ 子步骤状态：宏观规划
        self._update_shared_state(
            novel.novel_id.value,
            writing_substep="macro_planning",
            writing_substep_label="宏观规划",
        )

        target_chapters = novel.target_chapters or 30

        # 使用极速模式：structure_preference=None，让 AI 根据目标章节数智能决定结构
        # 这样 30 章、100 章、300 章、500 章会自动生成不同规模的叙事骨架
        result = await self.planning_service.generate_macro_plan(
            novel_id=novel.novel_id.value,
            target_chapters=target_chapters,
            structure_preference=None,
        )

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 宏观规划 LLM 返回后检测到停止，不再落库")
            return

        await self.planning_service.apply_macro_plan_from_llm_result(
            result,
            novel_id=novel.novel_id.value,
            target_chapters=target_chapters,
            minimal_fallback_on_empty=True,
        )

        # ⏸ 幕级大纲已就绪，进入人工审阅点（先落库再记日志，防止未保存导致下轮仍跑宏观规划）
        # 全自动模式：跳过审阅，直接进入幕级规划
        if getattr(novel, 'auto_approve_mode', False):
            novel.current_stage = NovelStage.ACT_PLANNING
            self._flush_novel(novel)
            # 🔥 宏观规划完成：同步故事线到共享内存（甘特图实时可见）
            self._sync_storylines_to_shared_memory(novel.novel_id.value)
            logger.info(f"[{novel.novel_id}] 🚀 全自动模式：宏观规划完成，直接进入幕级规划")
        else:
            novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
            self._flush_novel(novel)
            # 🔥 宏观规划完成：同步故事线到共享内存（甘特图实时可见）
            self._sync_storylines_to_shared_memory(novel.novel_id.value)
            logger.info(f"[{novel.novel_id}] 宏观规划完成，进入审阅等待")

    async def _handle_act_planning(self, novel: Novel):
        """处理幕级规划（插入缓冲章策略 + 动态幕生成）"""
        if not self._is_still_running(novel):
            return

        # ★ 子步骤状态：幕级规划
        self._update_shared_state(
            novel.novel_id.value,
            writing_substep="act_planning",
            writing_substep_label=f"第 {novel.current_act + 1} 幕规划",
        )

        novel_id = novel.novel_id.value
        target_act_number = novel.current_act + 1  # 1-indexed

        # 提前计算结构推荐参数，供后续多处使用（避免动态幕生成失败时变量未定义）
        from application.blueprint.services.continuous_planning_service import calculate_structure_params
        target_chapters = novel.target_chapters or 100
        struct_params = calculate_structure_params(target_chapters)
        rec_chapters_per_act = struct_params["chapters_per_act"]
        rec_acts_per_volume = struct_params["acts_per_volume"]

        all_nodes = await self.story_node_repo.get_by_novel(novel_id)
        act_nodes = sorted(
            [n for n in all_nodes if n.node_type.value == "act"],
            key=lambda n: n.number
        )

        target_act = next((n for n in act_nodes if n.number == target_act_number), None)

        # 动态幕生成：超长篇可能只规划了部/卷框架，幕节点需要动态生成
        if not target_act:
            # 先尝试找到父卷节点
            volume_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "volume"],
                key=lambda n: n.number
            )

            # 🚨 安全检查：如果没有卷节点，说明宏观规划失败，重新规划
            if not volume_nodes:
                logger.error(
                    f"[{novel_id}] 宏观规划缺少卷节点！无法进行幕级规划。"
                    f"parts={len([n for n in all_nodes if n.node_type.value == 'part'])}, "
                    f"volumes=0, acts={len(act_nodes)}. "
                    f"触发重新规划..."
                )
                # 回退到宏观规划阶段重新生成
                novel.current_stage = NovelStage.MACRO_PLANNING
                novel.current_act = 0
                self._flush_novel(novel)
                return

            # 智能父卷选择：优先让当前卷填满（达到 rec_acts_per_volume 幕），再跳下一卷
            parent_volume = self._find_parent_volume_for_new_act(
                volume_nodes=volume_nodes,
                act_nodes=act_nodes,
                current_auto_chapters=novel.current_auto_chapters or 0,
                target_chapters=target_chapters,
                rec_acts_per_volume=rec_acts_per_volume,
                novel_id=novel.novel_id,
            )

            if parent_volume:
                logger.info(
                    f"[{novel.novel_id}] 🎯 动态生成第 {target_act_number} 幕"
                    f"（父卷：第 {parent_volume.number} 卷，每幕建议 {rec_chapters_per_act} 章）"
                )
                try:
                    # 使用最后一个幕作为参考（如果有）
                    last_act = act_nodes[-1] if act_nodes else None
                    if last_act:
                        await self.planning_service.create_next_act_auto(
                            novel_id=novel_id,
                            current_act_id=last_act.id
                        )
                    else:
                        # 完全没有幕节点，创建第一个幕
                        logger.info(f"[{novel.novel_id}] 创建首幕")
                        from domain.structure.story_node import StoryNode, NodeType, PlanningStatus, PlanningSource
                        first_act = StoryNode(
                            id=f"act-{novel_id}-1",
                            novel_id=novel_id,
                            parent_id=parent_volume.id,
                            node_type=NodeType.ACT,
                            number=1,
                            title="第一幕 · 开端",
                            description="故事起始，建立世界观与主角目标",
                            order_index=0,
                            planning_status=PlanningStatus.CONFIRMED,
                            planning_source=PlanningSource.AI_MACRO,
                            suggested_chapter_count=rec_chapters_per_act,
                        )
                        await self.story_node_repo.save(first_act)
                    
                    # 重新加载
                    all_nodes = await self.story_node_repo.get_by_novel(novel_id)
                    act_nodes = sorted(
                        [n for n in all_nodes if n.node_type.value == "act"],
                        key=lambda n: n.number
                    )
                    target_act = next((n for n in act_nodes if n.number == target_act_number), None)
                except Exception as e:
                    logger.warning(f"[{novel.novel_id}] 动态幕生成失败: {e}")

            if not target_act:
                logger.error(f"[{novel.novel_id}] 找不到第 {target_act_number} 幕，且动态生成失败，回退到宏观规划")
                novel.current_stage = NovelStage.MACRO_PLANNING
                novel.current_act = 0
                self._flush_novel(novel)
                return

        # 检查该幕下是否已有章节节点（避免重复规划）
        act_children = self.story_node_repo.get_children_sync(target_act.id)
        confirmed_chapters = [n for n in act_children if n.node_type.value == "chapter"]

        just_created_chapter_plan = False
        if not confirmed_chapters:
            # 使用结构计算引擎的推荐值作为 fallback（替代硬编码的 5）
            chapter_budget = target_act.suggested_chapter_count or rec_chapters_per_act
            if not target_act.suggested_chapter_count:
                logger.info(
                    f"[{novel.novel_id}] 幕 {target_act_number} 无 suggested_chapter_count，"
                    f"使用引擎推荐值 {rec_chapters_per_act}"
                )
            plan_result: Dict[str, Any] = {}
            try:
                plan_result = await self.planning_service.plan_act_chapters(
                    act_id=target_act.id,
                    custom_chapter_count=chapter_budget
                )
            except Exception as e:
                logger.warning(
                    f"[{novel.novel_id}] plan_act_chapters 未捕获异常: {e}",
                    exc_info=True,
                )
                plan_result = {}

            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 幕级规划返回后检测到停止，不再落库")
                return

            raw = plan_result.get("chapters")
            chapters_data: List[Dict[str, Any]] = raw if isinstance(raw, list) else []
            if not chapters_data:
                # 不再创建占位章节，直接报错停止
                logger.error(
                    f"[{novel.novel_id}] 幕 {target_act_number} 规划失败：未得到有效章节规划"
                )
                novel.consecutive_error_count = (novel.consecutive_error_count or 0) + 1
                if novel.consecutive_error_count >= 3:
                    novel.autopilot_status = AutopilotStatus.ERROR
                    logger.error(f"[{novel.novel_id}] 连续失败达3次，已挂起")
                self._flush_novel(novel)
                return

            await self.planning_service.confirm_act_planning(
                act_id=target_act.id,
                chapters=chapters_data
            )
            just_created_chapter_plan = True

        act_children = self.story_node_repo.get_children_sync(target_act.id)
        confirmed_chapters = [n for n in act_children if n.node_type.value == "chapter"]

        # current_act 为 0-based 幕索引（与 Novel 实体一致），勿写入 1-based 的 target_act_number
        novel.current_act = target_act_number - 1

        if not confirmed_chapters:
            logger.error(
                f"[{novel.novel_id}] 幕 {target_act_number} 仍无章节节点，下轮继续幕级规划"
            )
            novel.current_stage = NovelStage.ACT_PLANNING
            return

        # 仅在本轮「新落库」幕级章节规划时暂停审阅；用户确认后同幕已有节点则直接写作，避免反复弹审批
        # 全自动模式：跳过审阅，直接进入写作
        if just_created_chapter_plan:
            if getattr(novel, 'auto_approve_mode', False):
                novel.current_stage = NovelStage.WRITING
                self._flush_novel(novel)
                logger.info(f"[{novel.novel_id}] 🚀 全自动模式：第 {target_act_number} 幕规划完成，直接进入写作")
            else:
                novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
                self._flush_novel(novel)
                logger.info(f"[{novel.novel_id}] 第 {target_act_number} 幕规划完成，进入审阅等待")
        else:
            novel.current_stage = NovelStage.WRITING
            self._flush_novel(novel)
            logger.info(
                f"[{novel.novel_id}] 第 {target_act_number} 幕章节节点已存在，进入写作"
            )

    async def _handle_writing(self, novel: Novel):
        """处理写作（节拍级幂等落库 + 章节完整性保证）

        核心改进：
        1. 节拍内容累积，减少 DB 写入频率
        2. 章节完成前检查字数，不足则续写
        3. 中断时保存已完成节拍索引，下次从断点继续
        4. 最终完成条件：字数达标 或 所有节拍完成
        """
        if not self._is_still_running(novel):
            return

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
        next_chapter_node = await self._find_next_unwritten_chapter_async(novel)
        if not next_chapter_node:
            # 🔥 修复：找不到下一章时，检查当前幕是否全部写完
            if await self._current_act_fully_written(novel):
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
        outline = next_chapter_node.outline or next_chapter_node.description or next_chapter_node.title

        # 合并分章叙事节拍
        if self.knowledge_service:
            try:
                knowledge = self.knowledge_service.get_knowledge(novel.novel_id.value)
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
        logger.info(f"[{novel.novel_id}] 📖 开始写第 {chapter_num} 章：{outline[:60]}...")
        logger.info(f"[{novel.novel_id}]    进度: {current_chapters}/{target_chapters} 章（目标 {target_word_count} 字/章）")

        # ★ 子步骤状态：找到下一章
        self._update_shared_state(
            novel.novel_id.value,
            writing_substep="chapter_found",
            writing_substep_label="章节定位",
            current_chapter_number=chapter_num,
        )

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止，跳过本章（上下文组装前）")
            return

        # 4. 获取规划阶段的 BeatSheet（如果有）
        beat_sheet = await self._get_beat_sheet_for_chapter(novel.novel_id.value, chapter_num)
        if beat_sheet:
            logger.info(f"[{novel.novel_id}] 📋 使用规划阶段的 BeatSheet：{len(beat_sheet.scenes)} 个场景")

        # ★ 子步骤状态：开始组装上下文
        self._update_shared_state(
            novel.novel_id.value,
            writing_substep="context_assembly",
            writing_substep_label="组装上下文",
            current_chapter_number=chapter_num,
        )

        # 5. 组装上下文
        bundle = None
        context = ""
        if self.chapter_workflow:
            try:
                bundle = self.chapter_workflow.prepare_chapter_generation(
                    novel.novel_id.value, chapter_num, outline, scene_director=None
                )
                context = bundle["context"]
                logger.info(
                    f"[{novel.novel_id}]    上下文（workflow）: {len(context)} 字符, "
                    f"约 {bundle['context_tokens']} tokens"
                )
            except Exception as e:
                logger.warning(f"prepare_chapter_generation 失败，尝试降级：{e}")
                try:
                    bundle = self.chapter_workflow.build_fallback_chapter_bundle(
                        novel.novel_id.value, chapter_num, outline, scene_director=None, max_tokens=20000,
                    )
                    context = bundle["context"]
                except Exception as e2:
                    logger.warning(f"降级失败：{e2}")
                    bundle = None
        if bundle is None and self.context_builder:
            try:
                context = self.context_builder.build_context(
                    novel_id=novel.novel_id.value, chapter_number=chapter_num, outline=outline, max_tokens=20000,
                )
            except Exception as e:
                logger.warning(f"ContextBuilder.build_context 失败：{e}")

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（上下文组装后）")
            return

        voice_anchors = ""
        if bundle is not None:
            voice_anchors = bundle.get("voice_anchors") or ""
        elif self.context_builder:
            try:
                voice_anchors = self.context_builder.build_voice_anchor_system_section(novel.novel_id.value)
            except Exception:
                voice_anchors = ""

        # 6. 节拍放大（优先使用 BeatSheet 的预估字数）
        beats = []
        if self.context_builder:
            beats = self.context_builder.magnify_outline_to_beats(
                chapter_num, outline,
                target_chapter_words=target_word_count,
                beat_sheet=beat_sheet,  # 传递规划阶段的 BeatSheet
            )

        # ★ 子步骤状态：节拍拆分完成
        self._update_shared_state(
            novel.novel_id.value,
            writing_substep="beat_magnification",
            writing_substep_label=f"节拍拆分（{len(beats)}个）",
            total_beats=len(beats),
            context_tokens=bundle.get('context_tokens', 0) if bundle else 0,
        )

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（节拍拆分后）")
            return

        # 6. 节拍级生成 + 断点续写 + 完整性保证
        start_beat = novel.current_beat_index or 0
        beats_completed = getattr(novel, 'beats_completed', False)
        chapter_content = await self._get_existing_chapter_content(novel, chapter_num) or ""
        use_wf = self.chapter_workflow is not None and bundle is not None

        # 断点续写：使用已有的章节内容作为上下文
        existing_content = chapter_content.strip()

        # === 关键检查：章节是否已完成 ===
        # 🔥 修复：审计完成后回到 WRITING，这一章已经审计过了（completed+已审计），
        # 不应再进入 AUDITING 重复审计。应跳过这一章，下一轮找新的未写章节。
        existing_chapter = self.chapter_repository.get_by_novel_and_number(
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
                self._flush_novel(novel)
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
                    self._save_chapter_ephemeral(
                        novel.novel_id.value, chapter_num,
                        status="completed",
                    )
                else:
                    await self._upsert_chapter_content(
                        novel, next_chapter_node, existing_content, status="completed"
                    )
                # return 让下一轮主循环重新进入 _handle_writing
                # 此时 DB 中章节已是 completed，_find_next_unwritten_chapter_async 会跳过它
                return
            logger.info(
                f"[{novel.novel_id}] 章节 {chapter_num} 已有 {len(existing_content)} 字 "
                f"(达标 {int(len(existing_content) / target_word_count * 100)}%)，直接标记完成"
            )
            await self._upsert_chapter_content(
                novel, next_chapter_node, existing_content, status="completed"
            )
            novel.current_auto_chapters = (novel.current_auto_chapters or 0) + 1
            novel.current_chapter_in_act += 1
            novel.current_beat_index = 0
            novel.beats_completed = False
            novel.current_stage = NovelStage.AUDITING
            self._flush_novel(novel)
            return

        # 如果节拍已完成，重置状态开始新章节
        if beats_completed:
            logger.info(f"[{novel.novel_id}] 节拍已标记完成，重置状态开始新章节")
            start_beat = 0
            novel.current_beat_index = 0
            novel.beats_completed = False

        # 关键检查：如果 start_beat 超出节拍范围，重置为 0
        # 这可能发生在：之前用错误的逻辑存储了节拍索引
        if start_beat >= len(beats):
            logger.warning(
                f"[{novel.novel_id}] 节拍索引 {start_beat} 超出范围 {len(beats)}，重置为 0"
            )
            start_beat = 0
            novel.current_beat_index = 0
            novel.beats_completed = False

        if existing_content and start_beat > 0:
            logger.info(
                f"[{novel.novel_id}] 断点续写：已有 {len(existing_content)} 字，"
                f"从第 {start_beat + 1}/{len(beats)} 个节拍继续"
            )

        # 批量写入计数器
        write_counter = 0
        BATCH_WRITE_INTERVAL = 3  # 每 3 个节拍写入一次 DB

        # 累积的章节内容
        accumulated_content = existing_content

        # 章节指挥（三阶段收束：铺陈→收束→着陆）
        from application.engine.services.word_count_tracker import ChapterConductor
        conductor = ChapterConductor(total_budget=target_word_count, total_beats=len(beats) if beats else 0)
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
            for i, beat in enumerate(beats):
                if i < start_beat:
                    continue  # 跳过已生成的节拍

                # 获取指挥信号（铺陈/收束/着陆）——须在共享状态写入前取得，供遥测字段使用
                signal = conductor.get_signal(i)

                # 🔥 节拍开始前，立即更新共享状态（前端实时看到当前节拍）
                beat_focus = getattr(beat, 'focus', '') or ''
                beat_target_words = getattr(beat, 'target_words', 0) or 0
                self._update_shared_state(
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
                    beat_hard_cap=int(signal.hard_cap or 0),
                    beat_phase=signal.phase.value,
                    beat_max_words_hint=int(signal.max_words_hint or 0),
                    beat_remaining_budget=int(signal.remaining_budget),
                    last_smart_truncate=None,
                )

                if not self._is_still_running(novel):
                    logger.info(f"[{novel.novel_id}] 用户已停止，中断本章（节拍 {i + 1}/{len(beats)} 前）")
                    # 保存已完成的内容和节拍索引
                    if accumulated_content.strip():
                        await self._upsert_chapter_content(
                            novel, next_chapter_node, accumulated_content, status="draft"
                        )
                        novel.current_beat_index = i  # 记录当前节拍索引，下次从断点继续
                        self._flush_novel(novel)
                        logger.info(
                            f"[{novel.novel_id}] 已保存 {len(accumulated_content)} 字，"
                            f"下次从节拍 {i + 1} 继续"
                        )
                    return

                adjusted_target = conductor.allocate_beat(beat.target_words, focus=beat.focus)  # ★ Phase 2: 传入 focus 用于免疫判断

                beat_prompt = self.context_builder.build_beat_prompt(beat, i, len(beats))

                # 🔗 V2：注入上一节拍的衔接诊断提示（如果有）
                if hasattr(novel, '_beat_continuity_hint') and novel._beat_continuity_hint:
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
                    prompt = self.chapter_workflow.build_chapter_prompt(
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
                    beat_content = await self._stream_llm_with_stop_watch(prompt, cfg, novel=novel)
                else:
                    beat_content = await self._stream_one_beat(
                        outline, context, beat_prompt, beat,
                        novel=novel, voice_anchors=voice_anchors,
                        chapter_draft_so_far=accumulated_content,
                    )

                if beat_content.strip():
                    # 智能截断安全网：超出硬上限时，截到完整句子边界
                    if signal.hard_cap > 0 and len(beat_content.strip()) > signal.hard_cap:
                        from application.engine.services.word_count_tracker import smart_truncate
                        original_len = len(beat_content.strip())
                        beat_content = smart_truncate(beat_content.strip(), signal.hard_cap)
                        logger.warning(
                            f"[{novel.novel_id}] ⚡ 智能截断：节拍 {i + 1} "
                            f"{original_len} → {len(beat_content)} 字 "
                            f"(硬上限 {signal.hard_cap} 字)"
                        )
                        self._update_shared_state(
                            novel.novel_id.value,
                            last_smart_truncate={
                                "beat_index_1based": i + 1,
                                "total_beats": len(beats),
                                "from_chars": original_len,
                                "to_chars": len(beat_content),
                                "hard_cap": int(signal.hard_cap),
                                "phase": signal.phase.value,
                            },
                        )

                    # ★ 子步骤状态：软着陆
                    self._update_shared_state(
                        novel.novel_id.value,
                        writing_substep="soft_landing",
                        writing_substep_label=f"节拍 {i+1}/{len(beats)} 收尾修整",
                    )

                    # 软着陆：截断检测与自然续写
                    beat_content = await self._soft_landing(
                        beat_content, beat, outline, accumulated_content, novel,
                        signal=signal,
                        emotion_trend=mw_ctx.emotion_trend,  # ★ Phase 2: 传入情绪方向
                    )

                    # 报告实际字数给指挥
                    actual_words = len(beat_content.strip())
                    deviation = conductor.report_actual(actual_words)
                    phase_emoji = {"unfurl": "📖", "converge": "⚡", "land": "🎯"}.get(signal.phase.value, "")
                    if deviation > 50:
                        logger.info(
                            f"[{novel.novel_id}] {phase_emoji} 节拍 {i + 1}/{len(beats)}: "
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
                                        f"[{novel.novel_id}] 🔗 节拍衔接度低 "
                                        f"beat={i+1}/{len(beats)} score={beat_score:.2f} "
                                        f"diag={beat_diag}"
                                    )
                                    if i < len(beats) - 1:
                                        continuity_fix_hint = (
                                            f"\n\n⚠️【节拍衔接诊断】上一节拍衔接度={beat_score:.2f}，"
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

                    # AOF：追加写入 .draft 文件（无锁 append，崩溃恢复用）
                    try:
                        from application.engine.services.draft_aof import append_chunk
                        append_chunk(novel.novel_id.value, chapter_num, "\n\n" + beat_content.strip() if accumulated_content != beat_content.strip() else beat_content.strip())
                    except Exception:
                        pass  # AOF 失败不影响主流程

                    # 批量写入（每 BATCH_WRITE_INTERVAL 个节拍或最后一个节拍时写入）
                    if write_counter >= BATCH_WRITE_INTERVAL or i == len(beats) - 1:
                        # ★ 子步骤状态：批量持久化
                        self._update_shared_state(
                            novel.novel_id.value,
                            writing_substep="persisting",
                            writing_substep_label="节拍内容落盘",
                        )
                        await self._upsert_chapter_content(
                            novel, next_chapter_node, accumulated_content, status="draft"
                        )
                        write_counter = 0
                        logger.debug(f"[{novel.novel_id}] 批量写入，当前 {len(accumulated_content)} 字")

                # 更新内存中的节拍索引用于流式推送
                novel.current_beat_index = i + 1

                # 🔥 同步更新共享内存的节拍索引（不写 DB，纳秒级）
                # 这样前端 /status 可以实时看到进度，不会因为 DB 锁而阻塞
                self._update_shared_state(
                    novel.novel_id.value,
                    current_beat_index=i + 1,
                    accumulated_words=len(accumulated_content),
                )

                # 如果是最后一个节拍，标记完成
                if i == len(beats) - 1:
                    novel.beats_completed = True
                    logger.info(f"[{novel.novel_id}] 📝 所有节拍已完成，标记 beats_completed = True")

                # 更新流式元数据
                if hasattr(self, '_update_stream_metadata'):
                    self._update_stream_metadata(novel.novel_id.value, i + 1, len(accumulated_content))

                logger.info(f"[{novel.novel_id}]    ✅ 节拍 {i+1}/{len(beats)} 完成: {len(beat_content)} 字")

            # 循环结束后，使用累积的内容
            chapter_content = accumulated_content
        else:
            # 降级：无节拍，一次生成
            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 用户已停止，跳过单段生成")
                return
            if use_wf:
                prompt = self.chapter_workflow.build_chapter_prompt(
                    bundle["context"], outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    voice_anchors=voice_anchors,
                )
                cfg = GenerationConfig(max_tokens=3000, temperature=0.85)
                beat_content = await self._stream_llm_with_stop_watch(prompt, cfg, novel=novel)
            else:
                beat_content = await self._stream_one_beat(
                    outline, context, None, None, novel=novel, voice_anchors=voice_anchors
                )
            if not self._is_still_running(novel):
                logger.info(f"[{novel.novel_id}] 用户已停止，单段生成已中断")
                novel.current_beat_index = 0
                self._flush_novel(novel)
                return
            chapter_content = beat_content
            await self._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="draft")

        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止，本章不标记完成")
            self._flush_novel(novel)
            return

        if use_wf and chapter_content.strip():
            try:
                await self.chapter_workflow.post_process_generated_chapter(
                    novel.novel_id.value, chapter_num, outline, chapter_content, scene_director=None
                )
                logger.info(f"[{novel.novel_id}]    ✅ post_process_generated_chapter 完成")
            except Exception as e:
                logger.warning(f"post_process_generated_chapter 失败（仍落库）：{e}")

        # 7. 章节完成检查（弹性边界策略）
        # ★ Phase 3: 提高弹性边界到 80%，并增加节拍完成度检查
        actual_word_count = len(chapter_content.strip())

        # 检测最后节拍是否是悬念收尾
        last_beat_is_suspense = beats and beats[-1].focus == "suspense" if beats else False

        # ★ Phase 3: 检测高能节拍是否存在（用于字数豁免）
        has_high_energy_beat = any(
            b.focus in ("action", "power_reveal", "identity_reveal", "hook", "cultivation")
            for b in (beats or [])
        )

        # ★ Phase 3: 计算节拍完成度
        beats_completed_count = sum(1 for b in (conductor.beats or []) if b.actual > 0)
        total_beats_count = len(beats) if beats else 0
        beats_completion_ratio = beats_completed_count / max(total_beats_count, 1)

        # 检测内容是否完整（以句号等结束符结尾）
        import re
        ending_pattern = r'[。！？…）】》"\'』」]$'
        content_complete = bool(re.search(ending_pattern, chapter_content.strip()))

        # ★ Phase 3: 弹性边界计算（提高阈值：60% 最低 / 80% 良好）
        min_word_threshold = int(target_word_count * 0.6)   # ★ Phase 3: 50% → 60%（拒绝"半成品"章节）
        good_word_threshold = int(target_word_count * 0.8)   # ★ Phase 3: 70% → 80%（要求更高质量）

        # 字数严重不足（低于 60%）：必须续写
        if actual_word_count < min_word_threshold:
            # ★ Phase 3: 例外——如果所有节拍都已完成且内容完整，仍然放行
            if total_beats_count > 0 and beats_completion_ratio >= 1.0 and content_complete:
                logger.info(
                    f"[{novel.novel_id}] 📝 弹性放行：所有节拍已完成且内容完整 "
                    f"(字数 {actual_word_count}，完成率 {int(actual_word_count / target_word_count * 100)}%)"
                )
                should_complete = True
                completion_reason = f"节拍完成+内容完整 (字数 {int(actual_word_count / target_word_count * 100)}%)"
            else:
                logger.warning(
                    f"[{novel.novel_id}] ⚠️ 第 {chapter_num} 章字数不足：{actual_word_count} 字 "
                    f"(目标 {target_word_count} 字，低于 60%)"
                )
                # 保持 draft 状态，下一轮继续生成
                self._flush_novel(novel)
                logger.info(f"[{novel.novel_id}] 章节保持 draft 状态，下一轮尝试续写")
                return
        else:
            should_complete = False
            completion_reason = ""

        if not should_complete:
            # ★ Phase 3: 基于字数、节拍完成度和高能节拍的弹性判断
            if actual_word_count >= good_word_threshold:
                # 字数达到 80% 以上
                should_complete = True
                completion_reason = f"字数达标 ({int(actual_word_count / target_word_count * 100)}%)"
            elif has_high_energy_beat and content_complete and actual_word_count >= min_word_threshold:
                # ★ Phase 3: 高能节拍豁免——包含爽点的章节，只要内容完整且字数≥60%即可放行
                should_complete = True
                completion_reason = f"高能节拍+内容完整 (字数 {int(actual_word_count / target_word_count * 100)}%)"
                logger.info(
                    f"[{novel.novel_id}] 📝 高能豁免放行：包含爽点节拍，内容完整，字数 {actual_word_count} 字"
                )
            elif last_beat_is_suspense and content_complete and actual_word_count >= min_word_threshold:
                # 悬念收尾 + 内容完整 + 字数 >= 60%
                should_complete = True
                completion_reason = f"悬念收尾 + 内容完整 (字数 {int(actual_word_count / target_word_count * 100)}%)"
                logger.info(
                    f"[{novel.novel_id}] 📝 弹性放行：悬念节拍自然收尾，字数 {actual_word_count} 字"
                )
            elif beats_completion_ratio >= 1.0 and content_complete and actual_word_count >= min_word_threshold:
                # ★ Phase 3: 所有节拍已完成 + 内容完整 + 字数≥60%
                should_complete = True
                completion_reason = f"节拍完成+内容完整 (字数 {int(actual_word_count / target_word_count * 100)}%)"
                logger.info(
                    f"[{novel.novel_id}] 📝 弹性放行：所有节拍已完成，字数 {actual_word_count} 字"
                )
            elif actual_word_count >= min_word_threshold and content_complete:
                # 内容完整 + 字数 >= 60%：允许通过但发出警告
                should_complete = True
                completion_reason = f"内容完整但字数偏低 ({int(actual_word_count / target_word_count * 100)}%)"
                logger.warning(
                    f"[{novel.novel_id}] ⚠️ 第 {chapter_num} 章字数略低：{actual_word_count} 字 "
                    f"(目标 {target_word_count} 字，完成率 {int(actual_word_count / target_word_count * 100)}%)"
                )

        if not should_complete:
            # 不满足放行条件，保持 draft 状态
            logger.warning(
                f"[{novel.novel_id}] ⚠️ 第 {chapter_num} 章未达到放行条件，保持 draft 状态"
            )
            self._flush_novel(novel)
            return

        # 8. 更新计数器，重置节拍状态
        novel.current_auto_chapters = (novel.current_auto_chapters or 0) + 1
        novel.current_chapter_in_act += 1
        novel.current_beat_index = 0
        novel.beats_completed = False  # 重置节拍完成标志
        novel.current_stage = NovelStage.AUDITING

        # 🔗 衔接引擎：章节完成后自检衔接度（非第 1 章）
        # 如果衔接度 < 0.6，自动修整首段（最多 2 轮）
        if chapter_num > 1:
            # ★ 子步骤状态：衔接自检
            self._update_shared_state(
                novel.novel_id.value,
                writing_substep="continuity_check",
                writing_substep_label="衔接度自检",
            )
            chapter_content = await self._continuity_self_check(
                novel.novel_id.value, chapter_num, chapter_content
            )

        # 🔥 先更新阶段到共享内存（不写章节聚合，避免占位 0 覆盖真实数据）
        self._update_shared_state(
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
        self._update_shared_state(
            novel.novel_id.value,
            writing_substep="chapter_persist",
            writing_substep_label="章节落盘",
        )
        await self._upsert_chapter_content(novel, next_chapter_node, chapter_content, status="completed")

        # 🔥 落库后用短连接读真实聚合，刷新 /status 缓存（与接口 SQL 一致）
        st = self._read_chapter_stats_ephemeral(novel.novel_id.value)
        if st:
            cc, mc, tw = st
            self._update_shared_state(
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

        self._flush_novel(novel)

        logger.info(
            f"[{novel.novel_id}] 🎉 第 {chapter_num} 章完成：{actual_word_count} 字 "
            f"(目标 {target_word_count} 字，共 {novel.current_auto_chapters}/{novel.target_chapters} 章)"
        )

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

        # 降级：直接通过主进程模块的函数写入（开发环境单进程时）
        try:
            from interfaces.main import update_shared_novel_state
            update_shared_novel_state(novel_id, **fields)
        except Exception:
            pass

    async def _handle_auditing(self, novel: Novel):
        """处理审计（含张力打分）

        核心架构优化：
        1. 高频状态（audit_progress、stage 等）写入共享内存，避免读库
        2. 只在审计完成时统一 save 到 DB，减少写锁持有时间
        3. /status 对章节聚合走短超时读库；共享内存中的 _cached_* 用于 DB 忙时的降级
        4. 每个 LLM 调用加超时保护，避免 deepseek API 卡住导致整个守护进程挂起
        5. 🔥 流式推送审计进度，让前端实时看到审计状态
        """
        if not self._is_still_running(novel):
            return

        chapter_num = self._latest_completed_chapter_number(NovelId(novel.novel_id.value))
        if chapter_num is None:
            novel.current_stage = NovelStage.WRITING
            self._update_shared_state(
                novel.novel_id.value,
                current_stage="writing",
                audit_progress=None,
            )
            return

        chapter = self.chapter_repository.get_by_novel_and_number(
            NovelId(novel.novel_id.value), chapter_num
        )
        if not chapter:
            novel.current_stage = NovelStage.WRITING
            self._update_shared_state(
                novel.novel_id.value,
                current_stage="writing",
                audit_progress=None,
            )
            return

        content = chapter.content or ""
        chapter_id = ChapterId(chapter.id)

        # 🔥 发布审计开始事件
        self._publish_audit_event(
            novel.novel_id.value,
            "audit_start",
            {"chapter_number": chapter_num, "word_count": len(content)}
        )

        # 1. 先做文风预检；若严重偏离则定向改写，最多两轮，再执行章后管线，避免分析结果与最终正文错位
        novel.audit_progress = "voice_check"
        # 🔥 架构优化：写共享内存，零 DB IO
        self._update_shared_state(
            novel.novel_id.value,
            current_stage="auditing",
            audit_progress="voice_check",
            last_chapter_number=chapter_num,
            writing_substep="audit_voice_check",
            writing_substep_label="文风预检",
        )
        # 🔥 发布文风预检事件
        self._publish_audit_event(
            novel.novel_id.value,
            "audit_voice_check",
            {"chapter_number": chapter_num}
        )
        drift_result = await self._call_with_timeout(
            self._score_voice_only(novel.novel_id.value, chapter_num, content),
            timeout=180.0,  # 文风预检最多 3 分钟
            novel_id=novel.novel_id.value,
            label="voice_check",
            fallback={"drift_alert": False, "similarity_score": None},
        )
        content, drift_result = await self._apply_voice_rewrite_loop(
            novel,
            chapter,
            content,
            drift_result,
        )
        # 🔥 发布文风预检结果事件
        self._publish_audit_event(
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
        self._update_shared_state(
            novel.novel_id.value,
            audit_progress="aftermath_pipeline",
            writing_substep="audit_aftermath",
            writing_substep_label="章后管线（叙事/向量/KG）",
        )
        # 🔥 发布章后管线事件
        self._publish_audit_event(
            novel.novel_id.value,
            "audit_aftermath",
            {"chapter_number": chapter_num}
        )
        if self.aftermath_pipeline:
            try:
                drift_result = await self._call_with_timeout(
                    self.aftermath_pipeline.run_after_chapter_saved(
                        novel.novel_id.value,
                        chapter_num,
                        content,
                    ),
                    timeout=300.0,  # 章后管线最多 5 分钟（含多次 LLM）
                    novel_id=novel.novel_id.value,
                    label="aftermath_pipeline",
                    fallback={"drift_alert": False, "similarity_score": None, "narrative_sync_ok": False, "vector_stored": False, "foreshadow_stored": False, "triples_extracted": False},
                )
                logger.info(
                    f"[{novel.novel_id}] 章后管线完成: 相似度={drift_result.get('similarity_score')}, "
                    f"drift_alert={drift_result.get('drift_alert')}"
                )
            except Exception as e:
                logger.warning(f"[{novel.novel_id}] 章后管线失败（降级旧逻辑）：{e}")
                drift_result = self._legacy_auditing_tasks_and_voice(
                    novel, chapter_num, content, chapter_id
                )
        else:
            drift_result = self._legacy_auditing_tasks_and_voice(
                novel, chapter_num, content, chapter_id
            )

        # ── 停止检查：章后管线和文风预检完成后 ──
        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（章后管线完成后），跳过张力打分")
            return

        # 2. 张力打分（轻量 LLM 调用，~200 token）
        novel.audit_progress = "tension_scoring"
        # 🔥 架构优化：写共享内存，零 DB IO
        self._update_shared_state(
            novel.novel_id.value,
            audit_progress="tension_scoring",
            writing_substep="audit_tension",
            writing_substep_label="张力打分",
        )
        # 🔥 发布张力打分事件
        self._publish_audit_event(
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
            old_scale_tension = await self._call_with_timeout(
                self._score_tension(content),
                timeout=60.0,
                novel_id=novel.novel_id.value,
                label="tension_scoring",
                fallback=5,
            )
            tension = old_scale_tension * 10  # 1-10 → 0-100
            logger.info(f"[{novel.novel_id}] 章节 {chapter_num} 旧式张力值：{old_scale_tension}/10 → {tension}/100")
        novel.last_chapter_tension = tension
        # 🔥 架构优化：审计期间只写共享内存，不写 DB，避免持锁导致前端卡死
        # DB 写入延迟到审计结束时统一落盘
        self._update_shared_state(
            novel.novel_id.value,
            last_chapter_tension=tension,
        )
        # 🔥 发布张力打分结果事件
        self._publish_audit_event(
            novel.novel_id.value,
            "audit_tension_result",
            {"tension": tension, "chapter_number": chapter_num}
        )
        logger.info(f"[{novel.novel_id}] 章节 {chapter_num} 张力值：{tension}/100（已写入共享内存）")

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
        similarity_below_threshold = self._similarity_below_warning_threshold(similarity_score)
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
        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（张力打分完成后），跳过落库")
            return

        novel.current_stage = NovelStage.WRITING
        novel.audit_progress = None  # 审计完成，清除进度标记
        novel.current_beat_index = 0  # 🔥 重置节拍索引，下一章从节拍 0 开始
        novel.beats_completed = False  # 🔥 重置节拍完成标志

        # 5. 全书完成检测（用轻量 COUNT 查询替代 list_by_novel，减少 DB 锁持有时间）
        completed_count = self._count_completed_chapters(NovelId(novel.novel_id.value))
        if completed_count >= novel.target_chapters:
            logger.info(f"[{novel.novel_id}] 🎉 全书完成！共 {completed_count} 章")
            novel.autopilot_status = AutopilotStatus.STOPPED
            novel.current_stage = NovelStage.COMPLETED

        # 🔥 发布审计完成事件
        self._publish_audit_event(
            novel.novel_id.value,
            "audit_complete",
            {
                "chapter_number": chapter_num,
                "tension": tension,
                "similarity_score": drift_result.get("similarity_score"),
                "completed_chapters": completed_count,
                "target_chapters": novel.target_chapters,
                "is_completed": completed_count >= novel.target_chapters,
            }
        )

        # 🔥 审计完成：统一 save 到 DB（低频、一次落盘）
        # 同时更新共享内存，让前端立刻感知
        st_stats = self._read_chapter_stats_ephemeral(novel.novel_id.value)
        if st_stats:
            cc_sig, mc_sig, tw_sig = st_stats
        else:
            cc_sig, mc_sig, tw_sig = completed_count, completed_count, 0

        self._update_shared_state(
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
        self._save_novel_ephemeral(novel)
        logger.info(f"[{novel.novel_id}] 审计完成，状态已落盘")

        # 🔥 审计完成：同步编年史+故事线到共享内存
        # narrative_sync 会更新故事线进度到 DB，这里重新加载确保共享内存同步
        self._sync_chronicles_to_shared_memory(novel.novel_id.value)
        self._sync_storylines_to_shared_memory(novel.novel_id.value)

        # 🔗 衔接引擎：审计完成后提取章节桥段（供下一章首段衔接使用）
        await self._extract_chapter_bridge(novel.novel_id.value, chapter_num, content)

        # 🛡️ Anti-AI 审计管线：对生成的章节进行 AI 味检测与审计
        await self._run_anti_ai_audit(novel.novel_id.value, chapter_num, content)

        # ── 停止检查：审计落盘完成后 ──
        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（审计落盘后），跳过摘要生成")
            return

        # 6. 自动触发宏观诊断（卷完结或约 6 万字间隔；静默注入，无前端提案交互）
        await self._auto_trigger_macro_diagnosis(novel, completed_count)

        # ── 停止检查：宏观诊断完成后 ──
        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 用户已停止（宏观诊断后），跳过摘要生成")
            return

        # 7. 🆕 摘要生成钩子（双轨融合 - 轨道一）
        await self._maybe_generate_summaries(novel, completed_count)

    async def _call_with_timeout(
        self,
        coro,
        timeout: float,
        novel_id: str = "",
        label: str = "",
        fallback=None,
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
            fallback: 超时/停止时的降级返回值
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
                logger.info(f"[{novel_id}] 🛑 {label} 完成但停止信号已触发，丢弃结果")
                return fallback

            return result

        except asyncio.TimeoutError:
            logger.warning(
                f"[{novel_id}] ⏱️ {label} 超时（{timeout}s），使用降级值: {fallback}"
            )
            if novel_id:
                self._update_shared_state(
                    novel_id,
                    _last_timeout_label=label,
                    _last_timeout_at=time.time(),
                )
            return fallback
        except Exception as e:
            logger.warning(f"[{novel_id}] {label} 异常: {e}，使用降级值")
            return fallback
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
            return float(similarity_score) < VOICE_WARNING_THRESHOLD_FALLBACK

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

    def _build_voice_rewrite_prompt(
        self,
        novel: Novel,
        chapter,
        content: str,
        similarity_score: float,
        attempt: int,
    ) -> Prompt:
        """构建定向修正文风的改写提示。"""
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

        system = f"""你是小说文风修订编辑。你的任务不是重写剧情，而是在不改变故事事实的前提下，修正文风偏移。

必须遵守：
1. 保留所有剧情事件、因果顺序、角色关系、伏笔信息、地点与关键信息。
2. 保留章节的主要段落结构、对话功能与情绪走向，不要扩写新支线。
3. 只调整叙述口吻、句式节奏、措辞密度、描写轻重，使文本更贴近既有作者文风。
4. 输出只能是修订后的完整章节正文，不要解释，不要加标题，不要加批注。

风格约束：
{style_block}

角色声线锚点：
{anchor_block}
"""
        user = f"""当前为第 {chapter.number} 章，第 {attempt} 次文风定向修正。

当前相似度：{similarity_score:.4f}
自动修文触发阈值：{VOICE_REWRITE_THRESHOLD:.2f}

章节大纲：
{outline}

请在不改变剧情事实的前提下，修订以下正文的叙述语气、句式节奏与措辞，使其更贴近既有文风：

{content}
"""
        return Prompt(system=system, user=user)

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

        prompt = self._build_voice_rewrite_prompt(
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
            result = await self.llm_service.generate(prompt, config)
        except Exception as e:
            logger.warning("[%s] 文风定向修文失败（attempt=%d）：%s", novel.novel_id, attempt, e)
            return None

        rewritten = strip_reasoning_artifacts((result.content or "").strip())
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
            logger.info(f"[{novel.novel_id}] 📊 自动触发宏观诊断：{trigger_reason}")

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
            
            logger.info(f"[{novel_id}] 📊 宏观诊断后台任务已启动")
            
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
                logger.warning(f"[{novel_id}] ⚠️ 宏观诊断失败：{result.error_message}")

        except Exception as e:
            logger.warning(f"[{novel_id}] 宏观诊断后台任务失败: {e}", exc_info=True)

    async def _score_tension(self, content: str) -> int:
        """给章节打张力分（1-10），用于判断是否插入缓冲章"""
        if not content or len(content) < 200:
            return 5  # 默认中等张力

        snippet = content[:500]  # 只取前 500 字，节省 token

        try:
            prompt = Prompt(
                system="你是小说节奏分析师，只输出一个 1-10 的整数，不要解释。",
                user=f"""根据以下章节开头，打分当前剧情的张力值（1=日常/轻松，10=生死对决/高潮）：

{snippet}

张力分（只输出数字）："""
            )
            config = GenerationConfig(max_tokens=5, temperature=0.1)
            result = await self.llm_service.generate(prompt, config)
            raw = result.content.strip() if hasattr(result, "content") else str(result).strip()
            score = int(''.join(filter(str.isdigit, raw[:3])))
            return max(1, min(10, score))
        except Exception:
            return 5  # 解析失败，返回默认值

    async def _stream_llm_with_stop_watch(
        self, prompt: Prompt, config: GenerationConfig, novel=None,
        total_timeout: float = 600.0, idle_timeout: float = 120.0,
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
        content = ""
        stop_detected = asyncio.Event()
        watch_task = None
        idle_watch_task = None
        nid = getattr(novel.novel_id, "value", novel.novel_id) if novel else None

        # 批量推送缓冲
        chunk_buffer: List[str] = []
        last_push_time = time.time()
        last_chunk_time = time.time()  # 追踪最后一次收到数据的时间
        # 🔥 高频小批量推送：实现真正的流式打字机效果
        # 每隔 0.15 秒推送一次，让前端有足够时间渲染，但又不会积攒太多
        CHUNK_PUSH_INTERVAL = 0.15
        start_time = time.time()

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
                    # 定期推送（每 0.15 秒），让前端有时间渲染
                    if current_time - last_push_time >= CHUNK_PUSH_INTERVAL:
                        await self._push_streaming_chunk(novel.novel_id.value, "".join(chunk_buffer))
                        chunk_buffer.clear()
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
            # 🔧 确保推送剩余的 chunks
            if novel is not None and chunk_buffer:
                await self._push_streaming_chunk(novel.novel_id.value, "".join(chunk_buffer))

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

    async def _push_streaming_chunk(self, novel_id: str, chunk: str):
        """推送增量文字到全局流式队列，供 SSE 接口消费
        
        🔥 同时更新心跳——流式生成可能持续 30-120 秒，
        期间前端需要知道守护进程仍在工作。
        """
        from application.engine.services.streaming_bus import streaming_bus
        streaming_bus.publish(novel_id, chunk)
        # 🔥 流式生成期间更新心跳，避免前端误判"后端无响应"
        self._write_daemon_heartbeat()

    def _update_stream_metadata(self, novel_id: str, beat_index: int, word_count: int):
        """更新流式元数据（供外部调用）"""
        from application.engine.services.streaming_bus import streaming_bus
        streaming_bus.update_beat(novel_id, beat_index, word_count)

    async def _soft_landing(
        self,
        content: str,
        beat: "Beat",
        outline: str,
        chapter_draft_so_far: str,
        novel=None,
        signal=None,
        emotion_trend: str = "stable",  # ★ Phase 2: rising/peak/falling/stable
    ) -> str:
        """V9: 软着陆——专业小说家的截断修复

        不是粗暴地"补句号"，而是像一个真正的作家那样处理：
        1. 先检测截断位置——是在对话中间？叙述中间？还是场景中间？
        2. 根据截断类型选择不同的续写策略
        3. 续写时参考大纲和前后文，确保结尾与章节弧线衔接
        4. 控制续写长度，避免续写过度
        ★ Phase 2: 情绪方向感知——根据前一节拍的情绪趋势决定收尾方式：
          - rising/peak: 用省略号或动作残影收尾（保留势能）
          - falling/stable: 用句号或完整结论收尾（闭合叙事）

        Args:
            content: 已生成的内容
            beat: 当前节拍对象
            outline: 章节大纲
            chapter_draft_so_far: 本章已生成的正文
            novel: 小说对象
            signal: ConductorSignal（指挥信号）
            emotion_trend: 情绪方向（★ Phase 2）

        Returns:
            完整的内容（可能包含续写部分）
        """
        import re

        if not content or not content.strip():
            return content

        # 🔥 停止信号检查：用户已停止时不发起续写 LLM 调用，直接返回已有内容
        if novel is not None and not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 软着陆跳过：用户已停止自动驾驶")
            return content

        stripped = content.rstrip()

        # 检测是否以句子结束符结尾
        ending_pattern = r'[。！？…）】》"\'』」]$'
        if re.search(ending_pattern, stripped):
            return content  # 结尾完整，无需续写

        # ── 诊断截断类型 ──
        truncation_type = self._diagnose_truncation(stripped)

        # ★ Phase 2: 情绪方向决定续写策略
        is_rising = emotion_trend in ("rising", "peak")

        # ── 确定续写预算 ──
        is_final_beat = signal.is_final_beat if signal else False
        if is_final_beat:
            # 最后节拍：允许稍长续写，确保章节有完整收尾
            max_continuation = 200
            continuation_role = "你是小说收尾助手。为被截断的章节最后一段提供自然、有画面感的收束。"
        elif truncation_type == "dialogue":
            # 对话中间截断：续写要简短，补完对话即可
            max_continuation = 100
            continuation_role = "你是小说续写助手。为被截断的对话提供简短自然的收尾，补完当前对话回合即可。"
        else:
            # 叙述/场景中间截断：中等续写
            max_continuation = 150
            continuation_role = "你是小说续写助手。为被截断的段落提供简短自然的收尾，让段落有完整的结尾。"

        logger.warning(
            f"[软着陆] 检测到截断（类型={truncation_type}，"
            f"最后节拍={is_final_beat}），发起续写（预算{max_continuation}字）"
        )

        # ── 构建续写 Prompt ──
        # 关键：给 LLM 足够的上下文，让它知道"该怎么收"
        context_snippet = stripped[-600:]  # 截断位置前文
        
        # 增加章节上下文，帮助续写保持连贯
        chapter_context_hint = ""
        if chapter_draft_so_far and len(chapter_draft_so_far) > 600:
            # 提供本章开头部分，帮助维持整体连贯性
            beginning_snippet = chapter_draft_so_far[:300]
            chapter_context_hint = f"\n本章开头参考：\n{beginning_snippet}...\n"
        
        outline_hint = ""
        if outline:
            # 取大纲最后部分作为方向指引
            outline_hint = f"\n章节大纲参考：\n{outline[-200:]}\n"

        final_beat_hint = ""
        if is_final_beat:
            final_beat_hint = (
                "\n这是本章最后一段。续写时：\n"
                "- 给出完整的段落结尾\n"
                "- 可以用一句有悬念感的话作为章节钩子\n"
                "- 不要强行总结全章\n"
                "- 确保与本章其他节拍形成完整的叙事弧线\n"
            )

        # 连贯性增强指南
        coherence_guide = ""
        if chapter_draft_so_far:
            coherence_guide = (
                "\n---连贯性要求---\n"
                "1. 续写内容必须与本章已生成的其他节拍保持情节连贯\n"
                "2. 保持相同的场景设定和人物状态\n"
                "3. 如果前文有未完成的情节线索，优先处理这些线索\n"
            )

        # ★ Phase 2: 情绪方向决定收尾风格
        emotion_guide = ""
        if is_rising:
            emotion_guide = (
                "\n---情绪方向指示---\n"
                "当前叙事情绪正在上升或达到高潮。续写时：\n"
                "- 用动作残影、未完的话语、或省略号收尾，保留叙事势能\n"
                "- 不要用句号「杀死」正在上升的张力——用破折号或省略号更好\n"
                "- 如果是战斗/对峙场景，留下一个未落下的动作\n"
            )
        else:
            emotion_guide = (
                "\n---情绪方向指示---\n"
                "当前叙事情绪在下降或平稳。续写时：\n"
                "- 给出完整的结论性收尾，用句号闭合\n"
                "- 可以用一个画面感强的小细节作为结束\n"
            )

        continuation_prompt = Prompt(
            system=continuation_role,
            user=f"""以下段落被截断了，请续写一个简短的结尾（{max_continuation}字以内）让它完整结束：

---截断的内容---
{context_snippet}
{chapter_context_hint}{outline_hint}{final_beat_hint}{coherence_guide}{emotion_guide}
---续写要求---
1. 承接上文语气和节奏，给出自然的收尾
2. 不要重复已有内容
3. 必须以完整句子结束
4. 字数控制在 {max_continuation} 字以内
5. 保持与上文一致的人物语气和叙事视角
6. 确保与本章整体情节发展相符

请直接续写，不要解释："""
        )

        try:
            config = GenerationConfig(max_tokens=int(max_continuation * 0.8), temperature=0.6)
            continuation = await self._stream_llm_with_stop_watch(
                continuation_prompt, config, novel=novel
            )

            if continuation and continuation.strip():
                # 拼接续写内容
                result = stripped + continuation.strip()
                # ★ Phase 2: 二次安全检查——根据情绪方向决定补全符
                if not re.search(ending_pattern, result.rstrip()):
                    if is_rising:
                        result = result.rstrip() + "……"  # 保留势能
                    else:
                        result = result.rstrip() + "。"  # 闭合叙事
                logger.info(f"[软着陆] 成功续写 {len(continuation.strip())} 字（截断类型={truncation_type}，情绪={emotion_trend}）")
                return result

        except Exception as e:
            logger.warning(f"[软着陆] 续写失败: {e}")

        # 续写失败——智能补结尾（不是粗暴加句号，而是截到上一个完整句子）
        result = self._fallback_close_sentence(stripped)
        return result

    def _diagnose_truncation(self, text: str) -> str:
        """诊断截断类型

        Returns:
            "dialogue" - 对话中间截断（有未闭合的引号）
            "narration" - 叙述中间截断（正常段落中间）
            "scene" - 场景中间截断（环境描写中间）
        """
        import re
        # 检查是否有未闭合的中文引号
        open_quotes = text.count('「') + text.count('"') + text.count('"')
        close_quotes = text.count('」') + text.count('"') + text.count('"')
        if open_quotes > close_quotes:
            return "dialogue"

        # 检查是否在环境描写中间（最后若干字没有对话标点）
        last_50 = text[-50:] if len(text) > 50 else text
        if not re.search(r'[「」""''：]', last_50) and re.search(r'[的着了过]', last_50[-5:]):
            return "scene"

        return "narration"

    def _fallback_close_sentence(self, text: str) -> str:
        """降级收尾：找到最后一个完整句子边界

        如果找不到好的边界，至少保证不留下半句话。
        """
        import re
        ending_pattern = r'[。！？…）】》"\'』」]'

        # 从后往前找最后一个句子结束符
        for i in range(len(text) - 1, max(len(text) - 200, -1), -1):
            if re.match(ending_pattern, text[i]):
                return text[:i + 1]

        # 实在找不到，补句号
        return text.rstrip() + "。"

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
        """无 AutoNovelGenerationWorkflow 时的降级：爽文短 Prompt + 流式。"""
        va = (voice_anchors or "").strip()
        voice_block = ""
        if va:
            voice_block = (
                "【角色声线与肢体语言（Bible 锚点，必须遵守）】\n"
                f"{va}\n\n"
            )
        system = f"""你是一位资深网文作家，擅长写爽文。
{voice_block}写作要求：
1. 严格按节拍字数和聚焦点写作
2. 必须有对话和人物互动，保持人物性格一致
3. 增加感官细节：视觉、听觉、触觉、情绪
4. 节奏控制：不要一章推进太多剧情
5. 不要写章节标题"""

        user_parts = []
        if context:
            user_parts.append(context)
        user_parts.append(f"\n【本章大纲】\n{outline}")
        prior = format_prior_draft_for_prompt(chapter_draft_so_far)
        if prior:
            user_parts.append(
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
                    user_parts.append(f"\n{directive}")
            except Exception:
                pass  # 降级：无锚点则不加

        if beat_prompt:
            user_parts.append(f"\n{beat_prompt}")
        user_parts.append("\n\n开始撰写：")

        # 字数控制策略（与主流程一致）
        max_tokens = int(beat.target_words * 1.3) if beat else 3000

        prompt = Prompt(system=system, user="\n".join(user_parts))
        config = GenerationConfig(max_tokens=max_tokens, temperature=0.85)
        return await self._stream_llm_with_stop_watch(prompt, config, novel=novel)

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

        content_str = (content or "").strip()
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
                logger.info(f"[{novel_id}] 📝 生成检查点摘要（第 {completed_count} 章）")
                result = await self.volume_summary_service.generate_checkpoint_summary(novel_id, completed_count)
                if result.success:
                    logger.info(f"[{novel_id}] ✅ 检查点摘要生成成功")
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
                            logger.info(f"[{novel_id}] 📝 生成幕摘要: {act.title}")
                            result = await self.volume_summary_service.generate_act_summary(novel_id, act.id)
                            if result.success:
                                logger.info(f"[{novel_id}] ✅ 幕摘要生成成功: {act.title}")
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
                        logger.info(f"[{novel_id}] 📝 生成卷摘要: {vol.title}")
                        result = await self.volume_summary_service.generate_volume_summary(novel_id, vol.number)
                        if result.success:
                            logger.info(f"[{novel_id}] ✅ 卷摘要生成成功: {vol.title}")
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
                            logger.info(f"[{novel_id}] 📝 生成部摘要: {part.title}")
                            result = await self.volume_summary_service.generate_part_summary(novel_id, part.number)
                            if result.success:
                                logger.info(f"[{novel_id}] ✅ 部摘要生成成功: {part.title}")
                            break
        
        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 摘要生成失败: {e}")

