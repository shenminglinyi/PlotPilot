"""状态发布器 - 守护进程的唯一写入入口

职责：
1. 更新共享状态（立即可见）
2. 推送持久化命令（异步）
3. 确保数据一致性

设计原则：
- 先写内存，再持久化
- 用户立即可见更新
- DB 作为持久化快照
"""
import logging
import time
from typing import Any, Dict, List, Optional

from application.engine.services.shared_state_repository import (
    SharedStateRepository,
    ChapterSummary,
    NovelState,
    get_shared_state_repository,
)

logger = logging.getLogger(__name__)


class StatePublisher:
    """状态发布器 - 守护进程的唯一写入入口

    🔥 核心原则：先写共享内存（立即可见），再推送持久化命令（异步）

    ✅ 使用适配器模式，透明切换新旧队列实现
    """

    def __init__(
        self,
        shared_state: Optional[SharedStateRepository] = None,
        persistence_queue=None,  # 支持注入队列实例
    ):
        self._shared = shared_state or get_shared_state_repository()

        # 使用适配器模式
        if persistence_queue is None:
            from application.engine.services.persistence_queue_adapter import get_persistence_queue_adapter
            self._queue = get_persistence_queue_adapter()
        else:
            self._queue = persistence_queue

        # 导入命令类型（兼容新旧实现）
        try:
            from application.engine.services.persistence_queue_v2 import PersistenceCommandType
        except ImportError:
            from application.engine.services.persistence_queue import PersistenceCommandType

        self._command_types = PersistenceCommandType

    # ==================== 小说状态 ====================

    def update_novel_state(self, novel_id: str, **fields):
        """更新小说状态

        先更新共享内存，再推送持久化命令。
        """
        # 1. 获取当前状态
        state = self._shared.get_novel_state(novel_id)
        if state is None:
            # 创建新状态
            state = NovelState(
                novel_id=novel_id,
                title=fields.get("title", ""),
                autopilot_status=fields.get("autopilot_status", "stopped"),
                current_stage=fields.get("current_stage", "writing"),
                current_act=fields.get("current_act"),
                current_chapter_in_act=fields.get("current_chapter_in_act"),
                current_beat_index=fields.get("current_beat_index", 0),
                current_auto_chapters=fields.get("current_auto_chapters", 0),
                target_chapters=fields.get("target_chapters", 0),
                target_words_per_chapter=fields.get("target_words_per_chapter", 2500),
                consecutive_error_count=fields.get("consecutive_error_count", 0),
                last_chapter_tension=fields.get("last_chapter_tension", 0),
                auto_approve_mode=fields.get("auto_approve_mode", False),
                needs_review=fields.get("needs_review", False),
            )
        else:
            # 更新字段
            for key, value in fields.items():
                if hasattr(state, key):
                    setattr(state, key, value)

        # 2. 更新共享内存
        self._shared.set_novel_state(novel_id, state)

        # 3. 更新守护进程心跳
        self._shared.update_daemon_heartbeat()

        # 4. 推送持久化命令（异步）
        self._queue.push(
            self._command_types.UPDATE_NOVEL_STATE.value,
            {"novel_id": novel_id, **state.to_dict()},
        )

    def set_autopilot_status(self, novel_id: str, status: str):
        """设置自动驾驶状态"""
        self.update_novel_state(novel_id, autopilot_status=status)

    def set_current_stage(self, novel_id: str, stage: str):
        """设置当前阶段"""
        self.update_novel_state(novel_id, current_stage=stage)

    def set_beat_index(self, novel_id: str, beat_index: int):
        """设置当前节拍索引"""
        self.update_novel_state(novel_id, current_beat_index=beat_index)

    def increment_auto_chapters(self, novel_id: str):
        """增加自动生成章节数"""
        state = self._shared.get_novel_state(novel_id)
        if state:
            self.update_novel_state(
                novel_id,
                current_auto_chapters=state.current_auto_chapters + 1,
            )

    # ==================== 章节操作 ====================

    def upsert_chapter(
        self,
        novel_id: str,
        chapter_id: str,
        chapter_number: int,
        title: str = "",
        status: str = "draft",
        word_count: int = 0,
        content: str = "",
    ):
        """更新或插入章节

        先更新共享内存，再推送持久化命令。
        """
        # 1. 创建章节摘要
        chapter = ChapterSummary(
            id=chapter_id,
            number=chapter_number,
            title=title,
            status=status,
            word_count=word_count,
        )

        # 2. 更新共享内存
        self._shared.update_chapter(novel_id, chapter)

        # 3. 更新守护进程心跳
        self._shared.update_daemon_heartbeat()

        # 4. 推送持久化命令
        self._queue.push(
            self._command_types.UPSERT_CHAPTER.value,
            {
                "novel_id": novel_id,
                "id": chapter_id,
                "number": chapter_number,
                "title": title,
                "status": status,
                "word_count": word_count,
                "content": content,
            },
        )

    def update_chapter_status(self, novel_id: str, chapter_number: int, status: str):
        """更新章节状态"""
        chapters = self._shared.get_chapters(novel_id)
        for c in chapters:
            if c.number == chapter_number:
                c.status = status
                self._shared.update_chapter(novel_id, c)
                break

        # 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_CHAPTER_STATUS.value,
            {
                "novel_id": novel_id,
                "chapter_number": chapter_number,
                "status": status,
            },
        )

    def update_chapter_word_count(
        self,
        novel_id: str,
        chapter_number: int,
        word_count: int,
    ):
        """更新章节字数"""
        chapters = self._shared.get_chapters(novel_id)
        for c in chapters:
            if c.number == chapter_number:
                c.word_count = word_count
                self._shared.update_chapter(novel_id, c)
                break

        # 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_CHAPTER_WORD_COUNT.value,
            {
                "novel_id": novel_id,
                "chapter_number": chapter_number,
                "word_count": word_count,
            },
        )

    # ==================== 伏笔操作 ====================

    def update_foreshadows(
        self,
        novel_id: str,
        entries: List[Dict[str, Any]],
    ):
        """更新伏笔列表"""
        # 1. 更新共享内存
        self._shared.set_foreshadows(novel_id, entries)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_FORESHADOWS.value,
            {"novel_id": novel_id, "entries": entries},
        )

    # ==================== 故事线操作 ====================

    def update_storylines(
        self,
        novel_id: str,
        storylines: List[Dict[str, Any]],
    ):
        """更新故事线列表"""
        # 1. 更新共享内存
        self._shared.set_storylines(novel_id, storylines)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_STORYLINES.value,
            {"novel_id": novel_id, "storylines": storylines},
        )

    # ==================== 剧情弧光操作 ====================

    def update_plot_arc(
        self,
        novel_id: str,
        arc: Dict[str, Any],
    ):
        """更新剧情弧光"""
        # 1. 更新共享内存
        self._shared.set_plot_arc(novel_id, arc)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_PLOT_ARC.value,
            {"novel_id": novel_id, "arc": arc},
        )

    # ==================== 编年史操作 ====================

    def update_chronicles(
        self,
        novel_id: str,
        rows: List[Dict[str, Any]],
    ):
        """更新编年史"""
        # 1. 更新共享内存
        self._shared.set_chronicles(novel_id, rows)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_CHRONICLES.value,
            {"novel_id": novel_id, "rows": rows},
        )

    # ==================== 叙事知识操作 ====================

    def update_knowledge(
        self,
        novel_id: str,
        knowledge: Dict[str, Any],
    ):
        """更新叙事知识"""
        # 1. 更新共享内存
        self._shared.set_knowledge(novel_id, knowledge)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_KNOWLEDGE.value,
            {"novel_id": novel_id, "knowledge": knowledge},
        )

    # ==================== 心跳 ====================

    def update_heartbeat(self):
        """更新守护进程心跳"""
        self._shared.update_daemon_heartbeat()

    # ==================== 批量操作 ====================

    def batch_update(self, novel_id: str, updates: Dict[str, Any]):
        """批量更新多个字段

        Args:
            novel_id: 小说 ID
            updates: 更新字段，如 {
                "novel_state": {...},
                "chapters": [...],
                "foreshadows": [...],
            }
        """
        if "novel_state" in updates:
            self.update_novel_state(novel_id, **updates["novel_state"])

        if "chapters" in updates:
            for chapter_data in updates["chapters"]:
                self._shared.update_chapter(novel_id, ChapterSummary(
                    id=chapter_data["id"],
                    number=chapter_data["number"],
                    title=chapter_data.get("title", ""),
                    status=chapter_data.get("status", "draft"),
                    word_count=chapter_data.get("word_count", 0),
                ))

        if "foreshadows" in updates:
            self.update_foreshadows(novel_id, updates["foreshadows"])

        if "storylines" in updates:
            self.update_storylines(novel_id, updates["storylines"])

        if "plot_arc" in updates:
            self.update_plot_arc(novel_id, updates["plot_arc"])

        if "chronicles" in updates:
            self.update_chronicles(novel_id, updates["chronicles"])

        if "knowledge" in updates:
            self.update_knowledge(novel_id, updates["knowledge"])

    # ==================== Bible 操作 ====================

    def update_bible(self, novel_id: str, bible: Dict[str, Any]):
        """更新 Bible"""
        # 1. 更新共享内存
        self._shared.set_bible(novel_id, bible)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_BIBLE.value,
            {"novel_id": novel_id, "bible": bible},
        )

    # ==================== 三元组操作 ====================

    def update_triples(self, novel_id: str, triples: List[Dict[str, Any]]):
        """更新三元组列表"""
        # 1. 更新共享内存
        self._shared.set_triples(novel_id, triples)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_TRIPLES.value,
            {"novel_id": novel_id, "triples": triples},
        )

    # ==================== 快照操作 ====================

    def update_snapshots(self, novel_id: str, snapshots: List[Dict[str, Any]]):
        """更新快照列表"""
        # 1. 更新共享内存
        self._shared.set_snapshots(novel_id, snapshots)

        # 2. 推送持久化命令
        self._queue.push(
            self._command_types.UPDATE_SNAPSHOTS.value,
            {"novel_id": novel_id, "snapshots": snapshots},
        )

    # ==================== 审计结果操作 ====================

    def update_last_audit(self, novel_id: str, audit: Dict[str, Any]):
        """更新最后一次审计结果"""
        # 只更新共享内存，不持久化（审计结果会通过章节更新持久化）
        self._shared.set_last_audit(novel_id, audit)

    def update_audit_progress(self, novel_id: str, progress: Dict[str, Any]):
        """更新审计进度"""
        # 只更新共享内存，审计进度不需要持久化
        self._shared.set_audit_progress(novel_id, progress)


# 全局实例（单例）
_state_publisher: Optional[StatePublisher] = None


def get_state_publisher() -> StatePublisher:
    """获取状态发布器实例"""
    global _state_publisher
    if _state_publisher is None:
        _state_publisher = StatePublisher()
    return _state_publisher


def init_state_publisher(
    shared_state: SharedStateRepository,
    persistence_queue: PersistenceQueue,
) -> StatePublisher:
    """初始化状态发布器"""
    global _state_publisher
    _state_publisher = StatePublisher(shared_state, persistence_queue)
    return _state_publisher
