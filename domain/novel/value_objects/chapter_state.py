from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass(frozen=True)
class ChapterState:
    """章节状态值对象

    包含从章节内容中提取的所有结构化信息
    """
    new_characters: List[Dict[str, Any]]  # List[{name, description, first_appearance}]
    character_actions: List[Dict[str, Any]]  # List[{character_id, action, chapter}]
    relationship_changes: List[Dict[str, Any]]  # List[{char1, char2, old_type, new_type, chapter}]
    foreshadowing_planted: List[Dict[str, Any]]  # List[{description, chapter}]
    foreshadowing_resolved: List[Dict[str, Any]]  # List[{foreshadowing_id, chapter}]
    events: List[Dict[str, Any]]  # List[{type, description, involved_characters, chapter}]
    timeline_events: List[Dict[str, Any]] = field(default_factory=list)  # List[{event, timestamp, timestamp_type}]
    advanced_storylines: List[Dict[str, Any]] = field(default_factory=list)  # List[{storyline_id, progress_summary}]
    new_storylines: List[Dict[str, Any]] = field(default_factory=list)  # List[{name, type, description}]

    def has_new_characters(self) -> bool:
        """检查是否有新角色"""
        return len(self.new_characters) > 0

    def has_relationship_changes(self) -> bool:
        """检查是否有关系变化"""
        return len(self.relationship_changes) > 0

    def has_foreshadowing_activity(self) -> bool:
        """检查是否有伏笔活动（埋下或解决）"""
        return len(self.foreshadowing_planted) > 0 or len(self.foreshadowing_resolved) > 0

    def has_timeline_events(self) -> bool:
        """检查是否有时间线事件"""
        return len(self.timeline_events) > 0

    def has_storyline_activity(self) -> bool:
        """检查是否有故事线活动（推进或新增）"""
        return len(self.advanced_storylines) > 0 or len(self.new_storylines) > 0
