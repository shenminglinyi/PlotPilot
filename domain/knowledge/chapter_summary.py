"""Chapter Summary entity"""
from typing import List, Dict, Any
from domain.shared.base_entity import BaseEntity


class ChapterSummary(BaseEntity):
    """章节叙事摘要实体"""

    def __init__(
        self,
        chapter_id: int,
        summary: str = "",
        key_events: str = "",
        open_threads: str = "",
        consistency_note: str = "",
        beat_sections: List[str] = None,
        micro_beats: List[Dict[str, Any]] = None,
        sync_status: str = "draft"
    ):
        """初始化章节摘要

        Args:
            chapter_id: 章节号
            summary: 章末总结
            key_events: 人物与关键事件
            open_threads: 埋线/未解问题
            consistency_note: 一致性说明
            beat_sections: 节拍子段落列表
            micro_beats: 微观节拍列表
            sync_status: 同步状态 (draft/synced/stale)
        """
        super().__init__(str(chapter_id))
        self.chapter_id = chapter_id
        self.summary = summary
        self.key_events = key_events
        self.open_threads = open_threads
        self.consistency_note = consistency_note
        self.beat_sections = beat_sections or []
        self.micro_beats = micro_beats or []
        self.sync_status = sync_status

    def __repr__(self) -> str:
        return f"<ChapterSummary chapter_id={self.chapter_id} status={self.sync_status}>"
