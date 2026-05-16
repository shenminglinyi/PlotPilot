# domain/novel/entities/novel.py
from enum import Enum
from typing import List, Optional, Dict, Any
from domain.shared.base_entity import BaseEntity
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.value_objects.story_phase import StoryPhase
from domain.shared.exceptions import InvalidOperationError


class NovelStage(str, Enum):
    """小说阶段（细化为自动驾驶状态机）"""
    PLANNING = "planning"  # 旧版兼容
    MACRO_PLANNING = "macro_planning"  # 规划部/卷/幕
    ACT_PLANNING = "act_planning"  # 规划当前幕的章节（插入缓冲章）
    WRITING = "writing"  # 写正文（节拍放大器）
    AUDITING = "auditing"  # 审计：文风、伏笔、图谱
    REVIEWING = "reviewing"  # 旧版兼容
    PAUSED_FOR_REVIEW = "paused_for_review"  # 幕完成，等待人工确认
    COMPLETED = "completed"


class AutopilotStatus(str, Enum):
    """自动驾驶状态"""
    STOPPED = "stopped"  # 人工接管/暂停
    RUNNING = "running"  # 全托管狂奔中
    ERROR = "error"  # 遇到阻断性错误，挂起等待急救


class Novel(BaseEntity):
    """小说聚合根"""

    def __init__(
        self,
        id: NovelId,
        title: str,
        author: str,
        target_chapters: int,
        premise: str = "",
        stage: NovelStage = NovelStage.PLANNING,
        autopilot_status: AutopilotStatus = AutopilotStatus.STOPPED,
        auto_approve_mode: bool = False,
        current_stage: NovelStage = NovelStage.PLANNING,
        current_act: int = 0,
        current_chapter_in_act: int = 0,
        max_auto_chapters: int = 9999,  # 保护上限，默认几乎无限制，由 target_chapters 控制实际完成点
        current_auto_chapters: int = 0,
        last_chapter_tension: int = 0,
        consecutive_error_count: int = 0,
        current_beat_index: int = 0,
        beats_completed: bool = False,  # 当前章节所有节拍是否已完成
        last_audit_chapter_number: Optional[int] = None,
        last_audit_similarity: Optional[float] = None,
        last_audit_drift_alert: bool = False,
        last_audit_narrative_ok: bool = True,
        last_audit_at: Optional[str] = None,
        # 章后管线状态
        last_audit_vector_stored: bool = False,
        last_audit_foreshadow_stored: bool = False,
        last_audit_triples_extracted: bool = False,
        last_audit_quality_scores: Optional[Dict[str, float]] = None,
        last_audit_issues: Optional[List[Dict[str, str]]] = None,
        # 目标字数控制
        target_words_per_chapter: int = 2500,
        # 审计进度指示
        audit_progress: Optional[str] = None,
    ):
        super().__init__(id.value)
        self.novel_id = id
        self.title = title
        self.author = author
        self.target_chapters = target_chapters
        self.premise = premise
        self.stage = stage
        self.chapters: List[Chapter] = []

        # 自动驾驶状态
        self.autopilot_status = autopilot_status
        self.auto_approve_mode = auto_approve_mode  # 全自动模式：跳过所有人工审阅
        self.current_stage = current_stage
        self.current_act = current_act
        self.current_chapter_in_act = current_chapter_in_act

        # 护城河字段
        self.max_auto_chapters = max_auto_chapters
        self.current_auto_chapters = current_auto_chapters
        self.last_chapter_tension = last_chapter_tension
        self.consecutive_error_count = consecutive_error_count
        self.current_beat_index = current_beat_index
        self.beats_completed = beats_completed

        # 全托管章末审阅快照
        self.last_audit_chapter_number = last_audit_chapter_number
        self.last_audit_similarity = last_audit_similarity
        self.last_audit_drift_alert = last_audit_drift_alert
        self.last_audit_narrative_ok = last_audit_narrative_ok
        self.last_audit_at = last_audit_at
        # 章后管线状态
        self.last_audit_vector_stored = last_audit_vector_stored
        self.last_audit_foreshadow_stored = last_audit_foreshadow_stored
        self.last_audit_triples_extracted = last_audit_triples_extracted
        self.last_audit_quality_scores = last_audit_quality_scores or {}
        self.last_audit_issues = last_audit_issues or []
        # 目标字数控制
        self.target_words_per_chapter = target_words_per_chapter
        # 审计进度指示
        self.audit_progress = audit_progress

    def add_chapter(self, chapter: Chapter) -> None:
        """添加章节（必须连续）"""
        expected_number = len(self.chapters) + 1
        if chapter.number != expected_number:
            raise InvalidOperationError(
                f"Chapter number must be {expected_number}, got {chapter.number}"
            )
        self.chapters.append(chapter)

    @property
    def completed_chapters(self) -> int:
        """已完成章节数"""
        return len([c for c in self.chapters if c.status == ChapterStatus.COMPLETED])

    def get_total_word_count(self):
        """获取总字数"""
        from domain.novel.value_objects.word_count import WordCount
        total = WordCount(0)
        for chapter in self.chapters:
            total = total + chapter.word_count
        return total

    def get_expected_total_words(self) -> int:
        """获取预期总字数"""
        return self.target_chapters * self.target_words_per_chapter

    # ─── StoryPhase 收敛沙漏（从engine核心注入）───

    def get_story_phase(self) -> StoryPhase:
        """根据写作进度计算当前故事阶段（全局收敛沙漏）

        收敛沙漏是剧情引擎的核心状态机：
        - 开局期(0-25%)：允许一切，铺陈悬念
        - 发展期(25-75%)：允许新伏笔，激化矛盾
        - 收敛期(75-90%)：禁止新伏笔，强制填坑
        - 终局期(90-100%)：终极对决，切断日常
        """
        if self.target_chapters <= 0:
            return StoryPhase.OPENING
        progress = self.completed_chapters / self.target_chapters
        return StoryPhase.from_progress(progress)

    def is_new_foreshadow_allowed(self) -> bool:
        """当前阶段是否允许新伏笔"""
        return self.get_story_phase().allow_new_foreshadow

    def is_new_plot_arc_allowed(self) -> bool:
        """当前阶段是否允许新剧情弧线"""
        return self.get_story_phase().allow_new_plot_arc

    # ─── Checkpoint HEAD指针（从engine核心注入）───

    current_checkpoint_id: Optional[str] = None

    def set_checkpoint_head(self, checkpoint_id: str) -> None:
        """设置当前Checkpoint HEAD指针"""
        self.current_checkpoint_id = checkpoint_id

    def get_checkpoint_head(self) -> Optional[str]:
        """获取当前Checkpoint HEAD指针"""
        return self.current_checkpoint_id
