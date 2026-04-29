"""后台任务服务 - 真实执行（战役二 v2）

设计理念：
1. 主线冲锋：写作流程不等待分析完成
2. 副线扇出：分析任务在后台线程异步执行
3. 最终一致性：分析结果最终会更新到数据库
4. 熔断保护：队列满时丢弃任务，避免内存爆炸
"""
import logging
import asyncio
import threading
import queue
import time
import uuid
from typing import Dict, Any, Optional
from enum import Enum

from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """后台任务类型"""

    VOICE_ANALYSIS = "voice_analysis"
    # 一次 LLM：章末叙事 + 三元组 + 伏笔 + 向量（与 ChapterAftermathPipeline 第一步同源）
    EXTRACT_BUNDLE = "extract_bundle"


class BackgroundTask:
    """后台任务"""
    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        novel_id: NovelId,
        chapter_id: ChapterId,
        payload: Dict[str, Any]
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.novel_id = novel_id
        self.chapter_id = chapter_id
        self.payload = payload


class BackgroundTaskService:
    """后台任务服务（工作线程模式）"""

    def __init__(
        self,
        voice_drift_service=None,
        llm_service=None,
        foreshadowing_repo=None,
        triple_repository=None,
        knowledge_service=None,
        chapter_indexing_service=None,
        storyline_repository=None,
        chapter_repository=None,
        plot_arc_repository=None,
        narrative_event_repository=None,
        obsidian_memory_service=None,
    ):
        self.voice_drift_service = voice_drift_service
        self.llm_service = llm_service
        self.foreshadowing_repo = foreshadowing_repo
        self.triple_repository = triple_repository
        self.knowledge_service = knowledge_service
        self.chapter_indexing_service = chapter_indexing_service
        self.storyline_repository = storyline_repository
        self.chapter_repository = chapter_repository
        self.plot_arc_repository = plot_arc_repository
        self.narrative_event_repository = narrative_event_repository
        self.obsidian_memory_service = obsidian_memory_service

        self._queue = queue.Queue(maxsize=200)  # 防队列无限增长
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="bg-task-worker")
        self._worker.start()
        logger.info("BackgroundTaskService worker thread started")

    def submit_task(self, task_type, novel_id, chapter_id, payload):
        """提交后台任务（非阻塞）"""
        try:
            task = BackgroundTask(
                task_id=str(uuid.uuid4()),
                task_type=task_type,
                novel_id=novel_id,
                chapter_id=chapter_id,
                payload=payload
            )
            self._queue.put_nowait(task)
            logger.debug(f"[BG] 任务已入队：{task_type.value}")
        except queue.Full:
            logger.warning(f"[BG] 后台任务队列已满，丢弃任务：{task_type.value}")

    def _worker_loop(self):
        """工作线程主循环"""
        while True:
            try:
                task = self._queue.get(timeout=2)
                self._execute_with_retry(task)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[BG] Worker loop error: {e}", exc_info=True)

    def _execute_with_retry(self, task, max_retries=2):
        """执行任务（带重试）"""
        for attempt in range(max_retries + 1):
            try:
                self._execute_task(task)
                return
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"[BG] 任务最终失败 {task.task_type.value}：{e}")
                else:
                    wait = 2 ** attempt  # 指数退避：1s, 2s
                    logger.warning(f"[BG] 任务失败，{wait}s 后重试：{e}")
                    time.sleep(wait)

    def _execute_task(self, task):
        """分发任务到具体处理器"""
        if task.task_type == TaskType.VOICE_ANALYSIS:
            self._handle_voice_analysis(task)
        elif task.task_type == TaskType.EXTRACT_BUNDLE:
            self._handle_extract_bundle(task)

    def _handle_voice_analysis(self, task):
        """文风分析处理器"""
        if not self.voice_drift_service:
            return
        content = task.payload.get("content", "")
        chapter_number = task.payload.get("chapter_number", 0)
        if not content:
            return

        self.voice_drift_service.score_chapter(
            novel_id=task.novel_id.value,
            chapter_number=chapter_number,
            content=content
        )
        logger.info(f"[BG] 文风分析完成：第 {chapter_number} 章")

    def _handle_extract_bundle(self, task):
        """章末 bundle：一次 LLM → 叙事落库 + 三元组 + 伏笔 + 故事线 + 张力 + 对话 + 向量（与管线 narrative_sync 一致）。"""
        if not self.llm_service or not self.knowledge_service:
            return
        content = (task.payload.get("content") or "").strip()
        chapter_number = int(task.payload.get("chapter_number") or 0)
        if not content:
            return

        from application.world.services.chapter_narrative_sync import sync_chapter_narrative_after_save

        try:
            asyncio.run(
                sync_chapter_narrative_after_save(
                    task.novel_id.value,
                    chapter_number,
                    content,
                    self.knowledge_service,
                    self.chapter_indexing_service,
                    self.llm_service,
                    triple_repository=self.triple_repository,
                    foreshadowing_repo=self.foreshadowing_repo,
                    storyline_repository=self.storyline_repository,
                    chapter_repository=self.chapter_repository,
                    plot_arc_repository=self.plot_arc_repository,
                    narrative_event_repository=self.narrative_event_repository,
                )
            )
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" not in str(e):
                raise
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    sync_chapter_narrative_after_save(
                        task.novel_id.value,
                        chapter_number,
                        content,
                        self.knowledge_service,
                        self.chapter_indexing_service,
                        self.llm_service,
                        triple_repository=self.triple_repository,
                        foreshadowing_repo=self.foreshadowing_repo,
                        storyline_repository=self.storyline_repository,
                        chapter_repository=self.chapter_repository,
                        plot_arc_repository=self.plot_arc_repository,
                        narrative_event_repository=self.narrative_event_repository,
                    )
                )
            finally:
                loop.close()
        if self.obsidian_memory_service:
            try:
                self.obsidian_memory_service.sync_chapter(task.novel_id.value, chapter_number)
            except Exception as e:
                logger.warning(
                    "[BG] Obsidian 长期记忆同步失败：novel=%s ch=%s err=%s",
                    task.novel_id.value,
                    chapter_number,
                    e,
                )
        logger.info(f"[BG] extract_bundle 完成：第 {chapter_number} 章")
