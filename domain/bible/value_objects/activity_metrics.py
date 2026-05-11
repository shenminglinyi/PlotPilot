from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ActivityMetrics:
    """角色活动度指标值对象

    跟踪角色在小说中的活跃程度，用于智能角色选择。
    """

    last_appearance_chapter: int = 0
    appearance_count: int = 0
    total_dialogue_count: int = 0
    last_updated: datetime = None

    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now(timezone.utc)

    def update_activity(self, chapter_number: int, dialogue_count: int = 0) -> None:
        """更新活动指标

        Args:
            chapter_number: 章节号
            dialogue_count: 对话数量（可选）
        """
        self.last_appearance_chapter = chapter_number
        self.appearance_count += 1
        self.total_dialogue_count += dialogue_count
        self.last_updated = datetime.now(timezone.utc)

    def is_active_since(self, chapter: int) -> bool:
        """判断角色是否在指定章节之后活跃

        Args:
            chapter: 章节号

        Returns:
            bool: 如果角色在该章节或之后出现过，返回 True
        """
        return self.last_appearance_chapter >= chapter
