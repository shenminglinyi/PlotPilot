"""Bible 数据传输对象"""
from dataclasses import dataclass, field
from typing import List, Optional, Any, TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from domain.bible.entities.bible import Bible
    from domain.bible.entities.character import Character
    from domain.bible.entities.world_setting import WorldSetting
    from domain.bible.entities.location import Location
    from domain.bible.entities.timeline_note import TimelineNote
    from domain.bible.entities.style_note import StyleNote


@dataclass
class CharacterDTO:
    """人物 DTO

    支持 POV 防火墙：
    - public_profile: 公开信息，总是可见
    - hidden_profile: 隐藏信息（如卧底身份），仅在 reveal_chapter 后可见
    - reveal_chapter: 揭示章节号，None 表示总是可见
    """
    id: str
    name: str
    description: str
    relationships: List[Any]
    public_profile: str = ""
    hidden_profile: str = ""
    reveal_chapter: Optional[int] = None
    mental_state: str = "NORMAL"
    mental_state_reason: str = ""
    verbal_tic: str = ""
    idle_behavior: str = ""
    core_belief: str = ""
    moral_taboos: List[str] = field(default_factory=list)
    voice_profile: Dict[str, Any] = field(default_factory=dict)
    active_wounds: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """验证字段"""
        if self.reveal_chapter is not None and self.reveal_chapter < 1:
            raise ValueError(f"reveal_chapter must be >= 1, got {self.reveal_chapter}")

    @classmethod
    def from_domain(cls, character: 'Character') -> 'CharacterDTO':
        """从领域对象创建 DTO

        Args:
            character: Character 领域对象

        Returns:
            CharacterDTO
        """
        return cls(
            id=character.character_id.value,
            name=character.name,
            description=character.description,
            relationships=character.relationships.copy(),
            public_profile=getattr(character, 'public_profile', ''),
            hidden_profile=getattr(character, 'hidden_profile', ''),
            reveal_chapter=getattr(character, 'reveal_chapter', None),
            mental_state=getattr(character, "mental_state", None) or "NORMAL",
            mental_state_reason=getattr(character, "mental_state_reason", None) or "",
            verbal_tic=getattr(character, "verbal_tic", None) or "",
            idle_behavior=getattr(character, "idle_behavior", None) or "",
            core_belief=getattr(character, "core_belief", None) or "",
            moral_taboos=list(getattr(character, "moral_taboos", None) or []),
            voice_profile=dict(getattr(character, "voice_profile", None) or {}),
            active_wounds=list(getattr(character, "active_wounds", None) or []),
        )


@dataclass
class WorldSettingDTO:
    """世界设定 DTO"""
    id: str
    name: str
    description: str
    setting_type: str

    @classmethod
    def from_domain(cls, setting: 'WorldSetting') -> 'WorldSettingDTO':
        """从领域对象创建 DTO

        Args:
            setting: WorldSetting 领域对象

        Returns:
            WorldSettingDTO
        """
        return cls(
            id=setting.id,
            name=setting.name,
            description=setting.description,
            setting_type=setting.setting_type
        )


@dataclass
class LocationDTO:
    """地点 DTO"""
    id: str
    name: str
    description: str
    location_type: str
    parent_id: Optional[str] = None

    @classmethod
    def from_domain(cls, location: 'Location') -> 'LocationDTO':
        """从领域对象创建 DTO

        Args:
            location: Location 领域对象

        Returns:
            LocationDTO
        """
        return cls(
            id=location.id,
            name=location.name,
            description=location.description,
            location_type=location.location_type,
            parent_id=location.parent_id,
        )


@dataclass
class TimelineNoteDTO:
    """时间线笔记 DTO"""
    id: str
    event: str
    time_point: str
    description: str

    @classmethod
    def from_domain(cls, note: 'TimelineNote') -> 'TimelineNoteDTO':
        """从领域对象创建 DTO

        Args:
            note: TimelineNote 领域对象

        Returns:
            TimelineNoteDTO
        """
        return cls(
            id=note.id,
            event=note.event,
            time_point=note.time_point,
            description=note.description
        )


@dataclass
class StyleNoteDTO:
    """风格笔记 DTO"""
    id: str
    category: str
    content: str

    @classmethod
    def from_domain(cls, note: 'StyleNote') -> 'StyleNoteDTO':
        """从领域对象创建 DTO

        Args:
            note: StyleNote 领域对象

        Returns:
            StyleNoteDTO
        """
        return cls(
            id=note.id,
            category=note.category,
            content=note.content
        )


@dataclass
class BibleDTO:
    """Bible DTO"""
    id: str
    novel_id: str
    characters: List[CharacterDTO]
    world_settings: List[WorldSettingDTO]
    locations: List[LocationDTO]
    timeline_notes: List[TimelineNoteDTO]
    style_notes: List[StyleNoteDTO]

    @classmethod
    def from_domain(cls, bible: 'Bible') -> 'BibleDTO':
        """从领域对象创建 DTO

        Args:
            bible: Bible 领域对象

        Returns:
            BibleDTO
        """
        return cls(
            id=bible.id,
            novel_id=bible.novel_id.value,
            characters=[CharacterDTO.from_domain(c) for c in bible.characters],
            world_settings=[WorldSettingDTO.from_domain(s) for s in bible.world_settings],
            locations=[LocationDTO.from_domain(loc) for loc in bible.locations],
            timeline_notes=[TimelineNoteDTO.from_domain(n) for n in bible.timeline_notes],
            style_notes=[StyleNoteDTO.from_domain(n) for n in bible.style_notes]
        )
