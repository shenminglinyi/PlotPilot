"""Bible 应用服务"""
from typing import TYPE_CHECKING, Optional

from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.entities.world_setting import WorldSetting
from domain.bible.entities.location import Location
from domain.bible.entities.timeline_note import TimelineNote
from domain.bible.entities.style_note import StyleNote
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.repositories.novel_repository import NovelRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.shared.exceptions import EntityNotFoundError
from application.world.dtos.bible_dto import BibleDTO, CharacterDTO

if TYPE_CHECKING:
    from application.world.services.bible_location_triple_sync import BibleLocationTripleSyncService


class BibleService:
    """Bible 应用服务"""

    def __init__(
        self,
        bible_repository: BibleRepository,
        novel_repository: Optional[NovelRepository] = None,
        chapter_repository: Optional[ChapterRepository] = None,
        location_triple_sync: Optional["BibleLocationTripleSyncService"] = None,
    ):
        """初始化服务

        Args:
            bible_repository: Bible 仓储
            location_triple_sync: 可选；保存 Bible 后将 locations 同步到 triples
        """
        self.bible_repository = bible_repository
        self._novel_repository = novel_repository
        self._chapter_repository = chapter_repository
        self._location_triple_sync = location_triple_sync

    def _validate_locations_forest(self, locations: list) -> None:
        from domain.bible.bible_location_tree import validate_location_forest

        forest = [{"id": ld.id, "parent_id": getattr(ld, "parent_id", None)} for ld in locations]
        validate_location_forest(forest)

    def _sync_location_triples(self, novel_id: str, bible: Bible) -> None:
        if self._location_triple_sync is None:
            return
        locs = [
            {
                "id": loc.id.strip(),
                "name": loc.name.strip(),
                "parent_id": loc.parent_id,
                "type": (loc.location_type or "").strip(),
            }
            for loc in bible.locations
        ]
        self._location_triple_sync.sync_from_locations(novel_id, locs)

    def create_bible(self, bible_id: str, novel_id: str) -> BibleDTO:
        """创建 Bible

        Args:
            bible_id: Bible ID
            novel_id: 小说 ID

        Returns:
            BibleDTO
        """
        # 兼容：部分入口可能先写 chapters/story_nodes，但 novels 主表尚未创建，导致 Bible 外键失败。
        # 这里兜底确保 novels(id) 存在，避免 500。
        if self._novel_repository is not None:
            existing = self._novel_repository.get_by_id(NovelId(novel_id))
            if existing is None:
                target = 30
                if self._chapter_repository is not None:
                    try:
                        n = len(self._chapter_repository.list_by_novel(NovelId(novel_id)))
                        target = max(target, n or 0)
                    except Exception:
                        pass
                placeholder = Novel(
                    id=NovelId(novel_id),
                    title=novel_id,
                    author="未知作者",
                    target_chapters=target,
                    premise="",
                    stage=NovelStage.PLANNING,
                )
                self._novel_repository.save(placeholder)

        bible = Bible(id=bible_id, novel_id=NovelId(novel_id))
        self.bible_repository.save(bible)
        return BibleDTO.from_domain(bible)

    def add_character(
        self,
        novel_id: str,
        character_id: str,
        name: str,
        description: str,
        relationships: list = None
    ) -> BibleDTO:
        """添加人物

        Args:
            novel_id: 小说 ID
            character_id: 人物 ID
            name: 人物名称
            description: 人物描述
            relationships: 人物关系列表

        Returns:
            更新后的 BibleDTO

        Raises:
            EntityNotFoundError: 如果 Bible 不存在
        """
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            raise EntityNotFoundError("Bible", f"for novel {novel_id}")

        character = Character(
            id=CharacterId(character_id),
            name=name,
            description=description,
            relationships=relationships or [],
        )
        bible.add_character(character)
        self.bible_repository.save(bible)

        return BibleDTO.from_domain(bible)

    def update_character_voice_anchors(
        self,
        novel_id: str,
        character_id: str,
        *,
        mental_state: str,
        verbal_tic: str,
        idle_behavior: str,
    ) -> CharacterDTO:
        """更新角色声线锚点（SQLite 行级更新）。"""
        repo = self.bible_repository
        if not hasattr(repo, "update_character_anchors"):
            raise NotImplementedError("仓储不支持角色锚点更新")
        repo.update_character_anchors(
            novel_id,
            character_id,
            mental_state=mental_state or "NORMAL",
            verbal_tic=verbal_tic or "",
            idle_behavior=idle_behavior or "",
        )
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            raise EntityNotFoundError("Bible", f"for novel {novel_id}")
        ch = bible.get_character(CharacterId(character_id))
        if ch is None:
            raise EntityNotFoundError("Character", character_id)
        return CharacterDTO.from_domain(ch)

    def build_character_voice_anchor_section(self, novel_id: str) -> str:
        """供章节/节拍 System 提示：非空锚点拼成一段。"""
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if not bible:
            return ""
        lines: list[str] = []
        for c in bible.characters:
            ms = (getattr(c, "mental_state", None) or "").strip()
            vt = (getattr(c, "verbal_tic", None) or "").strip()
            ib = (getattr(c, "idle_behavior", None) or "").strip()
            if not vt and not ib and (not ms or ms.upper() == "NORMAL"):
                continue
            parts = [f"- {c.name}"]
            if ms and ms.upper() != "NORMAL":
                parts.append(f"心理状态：{ms}")
            if vt:
                parts.append(f"口头禅：{vt}")
            if ib:
                parts.append(f"待机动作/小动作：{ib}")
            lines.append(" ".join(parts))
        return "\n".join(lines) if lines else ""

    def add_world_setting(
        self,
        novel_id: str,
        setting_id: str,
        name: str,
        description: str,
        setting_type: str
    ) -> BibleDTO:
        """添加世界设定

        Args:
            novel_id: 小说 ID
            setting_id: 设定 ID
            name: 设定名称
            description: 设定描述
            setting_type: 设定类型

        Returns:
            更新后的 BibleDTO

        Raises:
            EntityNotFoundError: 如果 Bible 不存在
        """
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            raise EntityNotFoundError("Bible", f"for novel {novel_id}")

        setting = WorldSetting(
            id=setting_id,
            name=name,
            description=description,
            setting_type=setting_type
        )
        bible.add_world_setting(setting)
        self.bible_repository.save(bible)

        return BibleDTO.from_domain(bible)

    def add_location(
        self,
        novel_id: str,
        location_id: str,
        name: str,
        description: str,
        location_type: str,
        connections: list = None,
        parent_id: Optional[str] = None,
    ) -> BibleDTO:
        """添加地点

        Args:
            novel_id: 小说 ID
            location_id: 地点 ID
            name: 地点名称
            description: 地点描述
            location_type: 地点类型
            connections: 地点关系列表

        Returns:
            更新后的 BibleDTO

        Raises:
            EntityNotFoundError: 如果 Bible 不存在
        """
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            raise EntityNotFoundError("Bible", f"for novel {novel_id}")

        pid = parent_id.strip() if isinstance(parent_id, str) and parent_id.strip() else None
        location = Location(
            id=location_id,
            name=name,
            description=description,
            location_type=location_type,
            connections=connections or [],
            parent_id=pid,
        )
        bible.add_location(location)
        from domain.bible.bible_location_tree import validate_location_forest

        validate_location_forest(
            [{"id": loc.id, "parent_id": loc.parent_id} for loc in bible.locations]
        )
        self.bible_repository.save(bible)
        self._sync_location_triples(novel_id, bible)

        return BibleDTO.from_domain(bible)

    def add_timeline_note(
        self,
        novel_id: str,
        note_id: str,
        event: str,
        time_point: str,
        description: str
    ) -> BibleDTO:
        """添加时间线笔记

        Args:
            novel_id: 小说 ID
            note_id: 笔记 ID
            event: 事件
            time_point: 时间点
            description: 描述

        Returns:
            更新后的 BibleDTO

        Raises:
            EntityNotFoundError: 如果 Bible 不存在
        """
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            raise EntityNotFoundError("Bible", f"for novel {novel_id}")

        note = TimelineNote(
            id=note_id,
            event=event,
            time_point=time_point,
            description=description
        )
        bible.add_timeline_note(note)
        self.bible_repository.save(bible)

        return BibleDTO.from_domain(bible)

    def add_style_note(
        self,
        novel_id: str,
        note_id: str,
        category: str,
        content: str
    ) -> BibleDTO:
        """添加风格笔记

        Args:
            novel_id: 小说 ID
            note_id: 笔记 ID
            category: 类别
            content: 内容

        Returns:
            更新后的 BibleDTO

        Raises:
            EntityNotFoundError: 如果 Bible 不存在
        """
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            raise EntityNotFoundError("Bible", f"for novel {novel_id}")

        note = StyleNote(
            id=note_id,
            category=category,
            content=content
        )
        bible.add_style_note(note)
        self.bible_repository.save(bible)

        return BibleDTO.from_domain(bible)

    def get_bible_by_novel(self, novel_id: str) -> Optional[BibleDTO]:
        """根据小说 ID 获取 Bible

        Args:
            novel_id: 小说 ID

        Returns:
            BibleDTO 或 None
        """
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            return None
        return BibleDTO.from_domain(bible)

    def update_bible(
        self,
        novel_id: str,
        characters: list,
        world_settings: list,
        locations: list,
        timeline_notes: list,
        style_notes: list
    ) -> BibleDTO:
        """批量更新 Bible 的所有数据

        Args:
            novel_id: 小说 ID
            characters: 人物列表
            world_settings: 世界设定列表
            locations: 地点列表
            timeline_notes: 时间线笔记列表
            style_notes: 风格笔记列表

        Returns:
            更新后的 BibleDTO

        Raises:
            EntityNotFoundError: 如果 Bible 不存在
        """
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))
        if bible is None:
            raise EntityNotFoundError("Bible", f"for novel {novel_id}")

        self._validate_locations_forest(locations)

        prev_chars = {c.character_id.value: c for c in bible.characters}

        # 清空现有数据
        bible._characters = []
        bible._world_settings = []
        bible._locations = []
        bible._timeline_notes = []
        bible._style_notes = []

        # 添加新的人物（锚点字段：请求未传则沿用库内旧值，避免整本保存冲掉沙盒写入）
        for char_data in characters:
            prev = prev_chars.get(char_data.id)
            if char_data.mental_state is not None:
                ms = char_data.mental_state or "NORMAL"
            elif prev is not None:
                ms = getattr(prev, "mental_state", None) or "NORMAL"
            else:
                ms = "NORMAL"
            if char_data.verbal_tic is not None:
                vt = char_data.verbal_tic or ""
            elif prev is not None:
                vt = getattr(prev, "verbal_tic", None) or ""
            else:
                vt = ""
            if char_data.idle_behavior is not None:
                ib = char_data.idle_behavior or ""
            elif prev is not None:
                ib = getattr(prev, "idle_behavior", None) or ""
            else:
                ib = ""
            if getattr(char_data, "mental_state_reason", None) is not None:
                msr = char_data.mental_state_reason or ""
            elif prev is not None:
                msr = getattr(prev, "mental_state_reason", None) or ""
            else:
                msr = ""
            if getattr(char_data, "public_profile", None) is not None:
                pub = char_data.public_profile or ""
            elif prev is not None:
                pub = getattr(prev, "public_profile", None) or ""
            else:
                pub = ""
            if getattr(char_data, "hidden_profile", None) is not None:
                hid = char_data.hidden_profile or ""
            elif prev is not None:
                hid = getattr(prev, "hidden_profile", None) or ""
            else:
                hid = ""
            if getattr(char_data, "reveal_chapter", None) is not None:
                rev = char_data.reveal_chapter
            elif prev is not None:
                rev = getattr(prev, "reveal_chapter", None)
            else:
                rev = None
            if getattr(char_data, "core_belief", None) is not None:
                cb = char_data.core_belief or ""
            elif prev is not None:
                cb = getattr(prev, "core_belief", None) or ""
            else:
                cb = ""
            if getattr(char_data, "moral_taboos", None) is not None:
                mt = list(char_data.moral_taboos or [])
            elif prev is not None:
                mt = list(getattr(prev, "moral_taboos", None) or [])
            else:
                mt = []
            if getattr(char_data, "voice_profile", None) is not None:
                vp = dict(char_data.voice_profile or {})
            elif prev is not None:
                vp = dict(getattr(prev, "voice_profile", None) or {})
            else:
                vp = {}
            if getattr(char_data, "active_wounds", None) is not None:
                aw = list(char_data.active_wounds or [])
            elif prev is not None:
                aw = list(getattr(prev, "active_wounds", None) or [])
            else:
                aw = []
            character = Character(
                id=CharacterId(char_data.id),
                name=char_data.name,
                description=char_data.description,
                relationships=char_data.relationships,
                public_profile=pub,
                hidden_profile=hid,
                reveal_chapter=rev,
                mental_state=ms,
                mental_state_reason=msr,
                verbal_tic=vt,
                idle_behavior=ib,
                core_belief=cb,
                moral_taboos=mt,
                voice_profile=vp,
                active_wounds=aw,
            )
            bible._characters.append(character)

        # 添加新的世界设定
        for setting_data in world_settings:
            setting = WorldSetting(
                id=setting_data.id,
                name=setting_data.name,
                description=setting_data.description,
                setting_type=setting_data.setting_type
            )
            bible._world_settings.append(setting)

        # 添加新的地点
        for loc_data in locations:
            raw_pid = getattr(loc_data, "parent_id", None)
            pid = raw_pid.strip() if isinstance(raw_pid, str) and raw_pid.strip() else None
            location = Location(
                id=loc_data.id,
                name=loc_data.name,
                description=loc_data.description,
                location_type=loc_data.location_type,
                parent_id=pid,
            )
            bible._locations.append(location)

        # 添加新的时间线笔记
        for note_data in timeline_notes:
            note = TimelineNote(
                id=note_data.id,
                event=note_data.event,
                time_point=note_data.time_point,
                description=note_data.description
            )
            bible._timeline_notes.append(note)

        # 添加新的风格笔记
        for note_data in style_notes:
            note = StyleNote(
                id=note_data.id,
                category=note_data.category,
                content=note_data.content
            )
            bible._style_notes.append(note)

        self.bible_repository.save(bible)
        self._sync_location_triples(novel_id, bible)
        return BibleDTO.from_domain(bible)
