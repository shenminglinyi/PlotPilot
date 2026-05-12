"""Bible 数据映射器"""
from typing import Dict, Any
from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.entities.world_setting import WorldSetting
from domain.bible.entities.location import Location
from domain.bible.entities.timeline_note import TimelineNote
from domain.bible.entities.style_note import StyleNote
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.value_objects.novel_id import NovelId


class BibleMapper:
    """Bible 实体与字典数据之间的映射器

    负责将 Bible 领域对象转换为可持久化的字典格式，
    以及从字典数据重建 Bible 对象。
    """

    @staticmethod
    def to_dict(bible: Bible) -> Dict[str, Any]:
        """将 Bible 实体转换为字典

        Args:
            bible: Bible 实体

        Returns:
            字典表示
        """
        return {
            "id": bible.id,
            "novel_id": bible.novel_id.value,
            "characters": [
                {
                    "id": char.character_id.value,
                    "name": char.name,
                    "description": char.description,
                    "relationships": char.relationships,
                    "mental_state": getattr(char, "mental_state", None) or "NORMAL",
                    "mental_state_reason": getattr(char, "mental_state_reason", None) or "",
                    "verbal_tic": getattr(char, "verbal_tic", None) or "",
                    "idle_behavior": getattr(char, "idle_behavior", None) or "",
                    "public_profile": getattr(char, "public_profile", None) or "",
                    "hidden_profile": getattr(char, "hidden_profile", None) or "",
                    "reveal_chapter": getattr(char, "reveal_chapter", None),
                    "core_belief": getattr(char, "core_belief", None) or "",
                    "moral_taboos": list(getattr(char, "moral_taboos", None) or []),
                    "voice_profile": dict(getattr(char, "voice_profile", None) or {}),
                    "active_wounds": list(getattr(char, "active_wounds", None) or []),
                }
                for char in bible.characters
            ],
            "world_settings": [
                {
                    "id": setting.id,
                    "name": setting.name,
                    "description": setting.description,
                    "setting_type": setting.setting_type
                }
                for setting in bible.world_settings
            ],
            "locations": [
                {
                    "id": loc.id,
                    "name": loc.name,
                    "description": loc.description,
                    "location_type": loc.location_type,
                    **({"parent_id": loc.parent_id} if loc.parent_id else {}),
                }
                for loc in bible.locations
            ],
            "timeline_notes": [
                {
                    "id": note.id,
                    "event": note.event,
                    "time_point": note.time_point,
                    "description": note.description
                }
                for note in bible.timeline_notes
            ],
            "style_notes": [
                {
                    "id": note.id,
                    "category": note.category,
                    "content": note.content
                }
                for note in bible.style_notes
            ]
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Bible:
        """从字典创建 Bible 实体

        Args:
            data: 字典数据

        Returns:
            Bible 实体

        Raises:
            ValueError: 如果数据格式不正确或缺少必需字段
        """
        # 验证必需字段
        required_fields = ["id", "novel_id"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        try:
            # 创建 Bible 实体
            bible = Bible(
                id=data["id"],
                novel_id=NovelId(data["novel_id"])
            )

            # 添加人物
            for char_data in data.get("characters", []):
                # 验证人物必需字段
                char_required = ["id", "name", "description"]
                char_missing = [field for field in char_required if field not in char_data]
                if char_missing:
                    raise ValueError(f"Character missing required fields: {', '.join(char_missing)}")

                rc = char_data.get("reveal_chapter")
                aw_raw = char_data.get("active_wounds") or []
                if isinstance(aw_raw, list):
                    active_wounds = [x for x in aw_raw if isinstance(x, dict)]
                else:
                    active_wounds = []
                character = Character(
                    id=CharacterId(char_data["id"]),
                    name=char_data["name"],
                    description=char_data["description"],
                    relationships=char_data.get("relationships", []),
                    public_profile=char_data.get("public_profile") or "",
                    hidden_profile=char_data.get("hidden_profile") or "",
                    reveal_chapter=rc if rc is not None else None,
                    mental_state=char_data.get("mental_state") or "NORMAL",
                    mental_state_reason=char_data.get("mental_state_reason") or "",
                    verbal_tic=char_data.get("verbal_tic") or "",
                    idle_behavior=char_data.get("idle_behavior") or "",
                    core_belief=char_data.get("core_belief") or "",
                    moral_taboos=list(char_data.get("moral_taboos") or []),
                    voice_profile=dict(char_data.get("voice_profile") or {}),
                    active_wounds=active_wounds,
                )
                bible.add_character(character)

            # 添加世界设定
            for setting_data in data.get("world_settings", []):
                # 验证世界设定必需字段
                setting_required = ["id", "name", "description", "setting_type"]
                setting_missing = [field for field in setting_required if field not in setting_data]
                if setting_missing:
                    raise ValueError(f"World setting missing required fields: {', '.join(setting_missing)}")

                setting = WorldSetting(
                    id=setting_data["id"],
                    name=setting_data["name"],
                    description=setting_data["description"],
                    setting_type=setting_data["setting_type"]
                )
                bible.add_world_setting(setting)

            # 添加地点
            for loc_data in data.get("locations", []):
                pid = loc_data.get("parent_id")
                parent_id = pid.strip() if isinstance(pid, str) and pid.strip() else None
                location = Location(
                    id=loc_data["id"],
                    name=loc_data["name"],
                    description=loc_data.get("description", ""),
                    location_type=loc_data.get("location_type", "other"),
                    parent_id=parent_id,
                )
                bible.add_location(location)

            # 添加时间线笔记
            for note_data in data.get("timeline_notes", []):
                note = TimelineNote(
                    id=note_data["id"],
                    event=note_data["event"],
                    time_point=note_data.get("time_point", ""),
                    description=note_data.get("description", "")
                )
                bible.add_timeline_note(note)

            # 添加风格笔记
            for note_data in data.get("style_notes", []):
                note = StyleNote(
                    id=note_data["id"],
                    category=note_data["category"],
                    content=note_data["content"]
                )
                bible.add_style_note(note)

            return bible
        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid bible data format: {str(e)}") from e
