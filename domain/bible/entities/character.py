from typing import List, Any, Optional, Dict
from domain.shared.base_entity import BaseEntity
from domain.bible.value_objects.character_id import CharacterId
from domain.shared.exceptions import InvalidOperationError


class Character(BaseEntity):
    """人物实体

    支持 POV 防火墙：
    - public_profile: 公开信息，总是可见
    - hidden_profile: 隐藏信息（如卧底身份），仅在 reveal_chapter 后可见
    - reveal_chapter: 揭示章节号，None 表示总是可见
    """

    def __init__(
        self,
        id: CharacterId,
        name: str,
        description: str,
        relationships: List[Any] = None,
        public_profile: str = "",
        hidden_profile: str = "",
        reveal_chapter: int = None,
        mental_state: str = "NORMAL",
        mental_state_reason: str = "",
        verbal_tic: str = "",
        idle_behavior: str = "",
        core_belief: str = "",
        moral_taboos: Optional[List[str]] = None,
        voice_profile: Optional[Dict[str, Any]] = None,
        active_wounds: Optional[List[Dict[str, str]]] = None,
    ):
        super().__init__(id.value)
        self.character_id = id
        self.name = name
        self.description = description
        self.relationships = relationships or []
        self.public_profile = public_profile
        self.hidden_profile = hidden_profile
        self.reveal_chapter = reveal_chapter
        self.mental_state = mental_state or "NORMAL"
        self.mental_state_reason = mental_state_reason or ""
        self.verbal_tic = verbal_tic or ""
        self.idle_behavior = idle_behavior or ""
        self.core_belief = core_belief or ""
        self.moral_taboos = list(moral_taboos or [])
        self.voice_profile = dict(voice_profile or {})
        self.active_wounds = list(active_wounds or [])

        # 验证 reveal_chapter
        if self.reveal_chapter is not None and self.reveal_chapter < 1:
            raise ValueError(f"reveal_chapter must be >= 1, got {self.reveal_chapter}")

    def add_relationship(self, relationship: Any) -> None:
        """添加关系（字符串或结构化 dict，与 Bible JSON / LLM 一致）"""
        if relationship in self.relationships:
            raise InvalidOperationError(f"Relationship already exists: {relationship}")
        self.relationships.append(relationship)

    def remove_relationship(self, relationship: str) -> None:
        """删除关系"""
        if relationship not in self.relationships:
            raise InvalidOperationError(f"Relationship not found: {relationship}")
        self.relationships.remove(relationship)

    def update_description(self, description: str) -> None:
        """更新描述"""
        if not description or not description.strip():
            raise ValueError("Description cannot be empty")
        self.description = description
