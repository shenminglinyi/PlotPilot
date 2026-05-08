"""共享状态仓库 - 内存优先读取的核心组件

职责：
1. 管理所有跨进程共享的状态数据
2. 提供统一的读写接口
3. 确保所有操作都是纳秒级内存访问，永不阻塞

设计原则：
- 所有查询都从共享内存读取
- 写入先更新内存，再异步持久化
- 数据结构轻量化，避免内存过大
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import multiprocessing as mp

logger = logging.getLogger(__name__)


@dataclass
class ChapterSummary:
    """章节摘要（轻量级，用于共享内存）"""
    id: str
    number: int
    title: str
    status: str
    word_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "status": self.status,
            "word_count": self.word_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterSummary":
        return cls(
            id=data["id"],
            number=data["number"],
            title=data.get("title", ""),
            status=data.get("status", "draft"),
            word_count=data.get("word_count", 0),
        )


@dataclass
class NovelState:
    """小说状态（用于共享内存）"""
    novel_id: str
    title: str
    autopilot_status: str
    current_stage: str
    current_act: Optional[int]
    current_chapter_in_act: Optional[int]
    current_beat_index: int
    current_auto_chapters: int
    target_chapters: int
    target_words_per_chapter: int
    consecutive_error_count: int
    last_chapter_tension: float
    auto_approve_mode: bool
    needs_review: bool
    _updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "title": self.title,
            "autopilot_status": self.autopilot_status,
            "current_stage": self.current_stage,
            "current_act": self.current_act,
            "current_chapter_in_act": self.current_chapter_in_act,
            "current_beat_index": self.current_beat_index,
            "current_auto_chapters": self.current_auto_chapters,
            "target_chapters": self.target_chapters,
            "target_words_per_chapter": self.target_words_per_chapter,
            "consecutive_error_count": self.consecutive_error_count,
            "last_chapter_tension": self.last_chapter_tension,
            "auto_approve_mode": self.auto_approve_mode,
            "needs_review": self.needs_review,
            "_updated_at": self._updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NovelState":
        return cls(
            novel_id=data["novel_id"],
            title=data.get("title", ""),
            autopilot_status=data.get("autopilot_status", "stopped"),
            current_stage=data.get("current_stage", "writing"),
            current_act=data.get("current_act"),
            current_chapter_in_act=data.get("current_chapter_in_act"),
            current_beat_index=data.get("current_beat_index", 0),
            current_auto_chapters=data.get("current_auto_chapters", 0),
            target_chapters=data.get("target_chapters", 0),
            target_words_per_chapter=data.get("target_words_per_chapter", 2500),
            consecutive_error_count=data.get("consecutive_error_count", 0),
            last_chapter_tension=data.get("last_chapter_tension", 0),
            auto_approve_mode=data.get("auto_approve_mode", False),
            needs_review=data.get("needs_review", False),
            _updated_at=data.get("_updated_at", time.time()),
        )


class SharedStateRepository:
    """共享状态仓库 - 所有查询的唯一入口

    使用 multiprocessing.Manager().dict() 实现跨进程共享。
    所有操作都是纯内存访问，纳秒级响应。
    """

    # 共享状态键前缀
    PREFIX_NOVEL = "novel:"
    KEY_DAEMON_HEARTBEAT = "_daemon_heartbeat"
    KEY_ALL_NOVELS = "_all_novels"

    def __init__(self, shared_dict: Optional[mp.Manager().dict] = None):
        """初始化共享状态仓库

        Args:
            shared_dict: 跨进程共享的字典（mp.Manager().dict()）
        """
        self._state = shared_dict

    def _ensure_state(self):
        """确保共享字典可用（延迟初始化）"""
        if self._state is None:
            try:
                from interfaces.main import _get_shared_state
                self._state = _get_shared_state()
                logger.debug("共享字典已从主进程获取")
            except Exception as e:
                logger.warning(f"无法获取共享字典: {e}")
        return self._state is not None

    def set_shared_dict(self, shared_dict: mp.Manager().dict):
        """设置共享字典（用于子进程注入）"""
        self._state = shared_dict

    # ==================== 小说状态 ====================

    def get_novel_state(self, novel_id: str) -> Optional[NovelState]:
        """获取小说状态"""
        if not self._ensure_state():
            return None

        key = f"{self.PREFIX_NOVEL}{novel_id}"
        data = self._state.get(key)
        if data is None:
            return None

        try:
            return NovelState.from_dict(data)
        except Exception as e:
            logger.warning(f"解析小说状态失败: {e}")
            return None

    def set_novel_state(self, novel_id: str, state: NovelState):
        """设置小说状态"""
        if not self._ensure_state():
            return

        state._updated_at = time.time()
        key = f"{self.PREFIX_NOVEL}{novel_id}"
        self._state[key] = state.to_dict()

        # 更新小说列表
        self._update_novel_list(novel_id)

    def update_novel_state(self, novel_id: str, **fields):
        """部分更新小说状态"""
        state = self.get_novel_state(novel_id)
        if state is None:
            return

        for key, value in fields.items():
            if hasattr(state, key):
                setattr(state, key, value)

        self.set_novel_state(novel_id, state)

    # ==================== 章节列表 ====================

    def get_chapters(self, novel_id: str) -> List[ChapterSummary]:
        """获取章节列表"""
        if not self._ensure_state():
            return []

        key = f"{self.PREFIX_NOVEL}{novel_id}:chapters"
        data = self._state.get(key, [])

        try:
            return [ChapterSummary.from_dict(c) for c in data]
        except Exception as e:
            logger.warning(f"解析章节列表失败: {e}")
            return []

    def set_chapters(self, novel_id: str, chapters: List[ChapterSummary]):
        """设置章节列表"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:chapters"
        self._state[key] = [c.to_dict() for c in chapters]

    def update_chapter(self, novel_id: str, chapter: ChapterSummary):
        """更新单个章节"""
        chapters = self.get_chapters(novel_id)

        # 查找并更新
        found = False
        for i, c in enumerate(chapters):
            if c.id == chapter.id or c.number == chapter.number:
                chapters[i] = chapter
                found = True
                break

        # 如果没找到，添加
        if not found:
            chapters.append(chapter)

        self.set_chapters(novel_id, chapters)

    # ==================== 伏笔列表 ====================

    def get_foreshadows(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取伏笔列表"""
        if not self._ensure_state():
            return []

        key = f"{self.PREFIX_NOVEL}{novel_id}:foreshadows"
        return self._state.get(key, [])

    def set_foreshadows(self, novel_id: str, entries: List[Dict[str, Any]]):
        """设置伏笔列表"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:foreshadows"
        self._state[key] = entries

    # ==================== 故事线 ====================

    def get_storylines(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取故事线列表"""
        if not self._ensure_state():
            return []

        key = f"{self.PREFIX_NOVEL}{novel_id}:storylines"
        return self._state.get(key, [])

    def set_storylines(self, novel_id: str, storylines: List[Dict[str, Any]]):
        """设置故事线列表"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:storylines"
        self._state[key] = storylines

    # ==================== 剧情弧光 ====================

    def get_plot_arc(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取剧情弧光"""
        if not self._ensure_state():
            return None

        key = f"{self.PREFIX_NOVEL}{novel_id}:plot_arc"
        return self._state.get(key)

    def set_plot_arc(self, novel_id: str, arc: Dict[str, Any]):
        """设置剧情弧光"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:plot_arc"
        self._state[key] = arc

    # ==================== 编年史 ====================

    def get_chronicles(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取编年史"""
        if not self._ensure_state():
            return []

        key = f"{self.PREFIX_NOVEL}{novel_id}:chronicles"
        return self._state.get(key, [])

    def set_chronicles(self, novel_id: str, rows: List[Dict[str, Any]]):
        """设置编年史"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:chronicles"
        self._state[key] = rows

    # ==================== 叙事知识 ====================

    def get_knowledge(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取叙事知识"""
        if not self._ensure_state():
            return None

        key = f"{self.PREFIX_NOVEL}{novel_id}:knowledge"
        return self._state.get(key)

    def set_knowledge(self, novel_id: str, knowledge: Dict[str, Any]):
        """设置叙事知识"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:knowledge"
        self._state[key] = knowledge

    # ==================== 心跳 ====================

    def update_daemon_heartbeat(self):
        """更新守护进程心跳"""
        if not self._ensure_state():
            return

        self._state[self.KEY_DAEMON_HEARTBEAT] = time.time()

    def get_daemon_heartbeat(self) -> Optional[float]:
        """获取守护进程心跳时间"""
        if not self._ensure_state():
            return None

        return self._state.get(self.KEY_DAEMON_HEARTBEAT)

    def is_daemon_alive(self, max_age_seconds: float = 60.0) -> bool:
        """检查守护进程是否存活"""
        heartbeat = self.get_daemon_heartbeat()
        if heartbeat is None:
            return False

        return (time.time() - heartbeat) < max_age_seconds

    # ==================== 小说列表 ====================

    def _update_novel_list(self, novel_id: str):
        """更新小说 ID 列表"""
        if not self._ensure_state():
            return

        all_novels = self._state.get(self.KEY_ALL_NOVELS, set())
        if isinstance(all_novels, list):
            all_novels = set(all_novels)
        all_novels.add(novel_id)
        self._state[self.KEY_ALL_NOVELS] = list(all_novels)

    def get_all_novel_ids(self) -> List[str]:
        """获取所有小说 ID"""
        if not self._ensure_state():
            return []

        return self._state.get(self.KEY_ALL_NOVELS, [])

    # ==================== 清理 ====================

    def clear_novel(self, novel_id: str):
        """清理指定小说的所有状态"""
        if not self._ensure_state():
            return

        keys_to_delete = [
            f"{self.PREFIX_NOVEL}{novel_id}",
            f"{self.PREFIX_NOVEL}{novel_id}:chapters",
            f"{self.PREFIX_NOVEL}{novel_id}:foreshadows",
            f"{self.PREFIX_NOVEL}{novel_id}:storylines",
            f"{self.PREFIX_NOVEL}{novel_id}:plot_arc",
            f"{self.PREFIX_NOVEL}{novel_id}:chronicles",
            f"{self.PREFIX_NOVEL}{novel_id}:knowledge",
            f"{self.PREFIX_NOVEL}{novel_id}:bible",
            f"{self.PREFIX_NOVEL}{novel_id}:triples",
            f"{self.PREFIX_NOVEL}{novel_id}:snapshots",
        ]

        for key in keys_to_delete:
            if key in self._state:
                del self._state[key]

        # 从小说列表中移除
        all_novels = self._state.get(self.KEY_ALL_NOVELS, [])
        if novel_id in all_novels:
            all_novels.remove(novel_id)
            self._state[self.KEY_ALL_NOVELS] = all_novels

    def get_raw_state(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取原始状态字典（用于兼容旧代码）"""
        if not self._ensure_state():
            return None

        key = f"{self.PREFIX_NOVEL}{novel_id}"
        return self._state.get(key)

    # ==================== Bible（世界观） ====================

    def get_bible(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取 Bible 数据"""
        if not self._ensure_state():
            return None

        key = f"{self.PREFIX_NOVEL}{novel_id}:bible"
        return self._state.get(key)

    def set_bible(self, novel_id: str, bible: Dict[str, Any]):
        """设置 Bible 数据"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:bible"
        self._state[key] = bible

    # ==================== 三元组（知识图谱） ====================

    def get_triples(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取三元组列表"""
        if not self._ensure_state():
            return []

        key = f"{self.PREFIX_NOVEL}{novel_id}:triples"
        return self._state.get(key, [])

    def set_triples(self, novel_id: str, triples: List[Dict[str, Any]]):
        """设置三元组列表"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:triples"
        self._state[key] = triples

    # ==================== 快照 ====================

    def get_snapshots(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取快照列表"""
        if not self._ensure_state():
            return []

        key = f"{self.PREFIX_NOVEL}{novel_id}:snapshots"
        return self._state.get(key, [])

    def set_snapshots(self, novel_id: str, snapshots: List[Dict[str, Any]]):
        """设置快照列表"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:snapshots"
        self._state[key] = snapshots

    # ==================== 审计结果 ====================

    def get_last_audit(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取最后一次审计结果"""
        if not self._ensure_state():
            return None

        key = f"{self.PREFIX_NOVEL}{novel_id}:last_audit"
        return self._state.get(key)

    def set_last_audit(self, novel_id: str, audit: Dict[str, Any]):
        """设置最后一次审计结果"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:last_audit"
        self._state[key] = audit

    # ==================== 审计进度 ====================

    def get_audit_progress(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取审计进度"""
        if not self._ensure_state():
            return None

        key = f"{self.PREFIX_NOVEL}{novel_id}:audit_progress"
        return self._state.get(key)

    def set_audit_progress(self, novel_id: str, progress: Dict[str, Any]):
        """设置审计进度"""
        if not self._ensure_state():
            return

        key = f"{self.PREFIX_NOVEL}{novel_id}:audit_progress"
        self._state[key] = progress


# 全局实例（单例）
_shared_state_repository: Optional[SharedStateRepository] = None


def init_shared_state_repository(shared_dict: mp.Manager().dict) -> SharedStateRepository:
    """初始化共享状态仓库（主进程调用）"""
    global _shared_state_repository
    _shared_state_repository = SharedStateRepository(shared_dict)
    return _shared_state_repository


def get_shared_state_repository() -> SharedStateRepository:
    """获取共享状态仓库实例"""
    global _shared_state_repository
    if _shared_state_repository is None:
        # 延迟初始化（用于子进程）
        _shared_state_repository = SharedStateRepository()
    return _shared_state_repository


def inject_shared_dict(shared_dict: mp.Manager().dict):
    """注入共享字典（子进程调用）"""
    global _shared_state_repository
    if _shared_state_repository is None:
        _shared_state_repository = SharedStateRepository()
    _shared_state_repository.set_shared_dict(shared_dict)
