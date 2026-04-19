import re
import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from domain.novel.value_objects.chapter_state import ChapterState
from domain.novel.value_objects.novel_id import NovelId
from domain.bible.entities.character import Character
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel
)
from domain.novel.value_objects.timeline_event import TimelineEvent
from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.repositories.timeline_repository import TimelineRepository
from domain.novel.repositories.storyline_repository import StorylineRepository
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.entities.timeline_registry import TimelineRegistry

logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_chapter_int(value: Any, fallback: int) -> int:
    """LLM 常在 chapter 字段填「本章」「当前章节」等，避免 int() 直接崩。"""
    if value is None:
        return fallback
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0))
    return fallback


class StateUpdater:
    """状态更新应用服务

    根据 ChapterState 更新各个领域对象
    """

    def __init__(
        self,
        bible_repository: BibleRepository,
        foreshadowing_repository: ForeshadowingRepository,
        timeline_repository: Optional[TimelineRepository] = None,
        storyline_repository: Optional[StorylineRepository] = None,
        knowledge_service=None,
        chapter_repository=None,
        db_connection=None
    ):
        self.bible_repository = bible_repository
        self.foreshadowing_repository = foreshadowing_repository
        self.timeline_repository = timeline_repository
        self.storyline_repository = storyline_repository
        self.knowledge_service = knowledge_service
        self.chapter_repository = chapter_repository
        self.db_connection = db_connection

    def update_from_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        chapter_state: ChapterState
    ) -> None:
        """从章节状态更新所有相关对象

        Args:
            novel_id: 小说ID
            chapter_number: 章节号
            chapter_state: 章节状态
        """
        chapter_number = _safe_chapter_int(chapter_number, 1)
        if chapter_number < 1:
            chapter_number = 1
        novel_id_obj = NovelId(novel_id)
        logger.info(
            f"StateUpdater.update_from_chapter: novel={novel_id}, chapter={chapter_number}, "
            f"new_characters={len(chapter_state.new_characters)}, "
            f"foreshadowing_planted={len(chapter_state.foreshadowing_planted)}, "
            f"foreshadowing_resolved={len(chapter_state.foreshadowing_resolved)}"
        )

        # 更新 Bible（新角色）
        if chapter_state.has_new_characters():
            logger.debug(f"Updating Bible with {len(chapter_state.new_characters)} new characters")
            bible = self.bible_repository.get_by_novel_id(novel_id_obj)
            if bible is None:
                logger.warning(f"Bible not found for novel {novel_id}, skipping character update")
            else:
                for char_data in chapter_state.new_characters:
                    char_id = CharacterId(str(uuid.uuid4()))
                    character = Character(
                        id=char_id,
                        name=char_data.get("name", "未知角色"),
                        description=char_data.get("description", "")
                    )
                    bible.add_character(character)
                    logger.debug(f"Added character: {char_data.get('name')}")

                self.bible_repository.save(bible)
                logger.info(f"Bible updated: added {len(chapter_state.new_characters)} new characters for novel {novel_id}")
        else:
            logger.debug("No new characters to add")

        # 更新 ForeshadowingRegistry（新伏笔和解决伏笔）
        if chapter_state.has_foreshadowing_activity():
            logger.debug(
                f"Updating ForeshadowingRegistry: "
                f"plant={len(chapter_state.foreshadowing_planted)}, "
                f"resolve={len(chapter_state.foreshadowing_resolved)}"
            )
            foreshadowing_registry = self.foreshadowing_repository.get_by_novel_id(novel_id_obj)
            if foreshadowing_registry is None:
                logger.info(f"ForeshadowingRegistry not found for novel {novel_id}, creating new one")
                foreshadowing_registry = ForeshadowingRegistry(
                    id=str(uuid.uuid4()),
                    novel_id=novel_id_obj
                )

            # 添加新伏笔
            for foreshadow_data in chapter_state.foreshadowing_planted:
                foreshadowing = Foreshadowing(
                    id=str(uuid.uuid4()),
                    planted_in_chapter=_safe_chapter_int(
                        foreshadow_data.get("chapter"), chapter_number
                    ),
                    description=foreshadow_data.get("description", ""),
                    importance=ImportanceLevel.MEDIUM,
                    status=ForeshadowingStatus.PLANTED
                )
                foreshadowing_registry.register(foreshadowing)
                logger.debug(f"Planted foreshadowing: {foreshadow_data.get('description', '')[:50]}")

            # 解决伏笔
            for resolved_data in chapter_state.foreshadowing_resolved:
                fid = self._resolve_foreshadowing_id(foreshadowing_registry, resolved_data)
                resolved_ch = _safe_chapter_int(
                    resolved_data.get("chapter"), chapter_number
                )
                if not fid:
                    logger.warning("Skipping foreshadowing resolution with no identifiable reference: %s", resolved_data)
                    continue
                try:
                    foreshadowing_registry.mark_resolved(
                        foreshadowing_id=fid,
                        resolved_in_chapter=resolved_ch
                    )
                    logger.debug(f"Resolved foreshadowing: {fid}")
                except Exception as e:
                    logger.warning(f"Failed to resolve foreshadowing {fid}: {e}")

            self.foreshadowing_repository.save(foreshadowing_registry)
            logger.info(f"ForeshadowingRegistry updated for novel {novel_id}")
        else:
            logger.debug("No foreshadowing activity to update")

        # 更新 TimelineRegistry（时间线事件 - 第一梯队）
        if self.timeline_repository and chapter_state.has_timeline_events():
            logger.debug(f"Updating TimelineRegistry: {len(chapter_state.timeline_events)} events")
            timeline_registry = self.timeline_repository.get_by_novel_id(novel_id_obj)
            if timeline_registry is None:
                logger.info(f"TimelineRegistry not found for novel {novel_id}, creating new one")
                timeline_registry = TimelineRegistry(
                    id=str(uuid.uuid4()),
                    novel_id=novel_id_obj
                )

            # 添加时间线事件
            for event_data in chapter_state.timeline_events:
                timeline_event = TimelineEvent(
                    id=str(uuid.uuid4()),
                    chapter_number=chapter_number,
                    event=event_data.get("event", ""),
                    timestamp=event_data.get("timestamp", ""),
                    timestamp_type=event_data.get("timestamp_type", "vague")
                )
                timeline_registry.add_event(timeline_event)
                logger.debug(f"Added timeline event: {event_data.get('event', '')[:50]}")

            self.timeline_repository.save(timeline_registry)
            logger.info(f"TimelineRegistry updated for novel {novel_id}")
        else:
            logger.debug("No timeline events to update")

        # 更新 Storyline（故事线进度 - 第二梯队）
        if self.storyline_repository and chapter_state.has_storyline_activity():
            logger.debug(
                f"Updating Storylines: "
                f"advanced={len(chapter_state.advanced_storylines)}, "
                f"new={len(chapter_state.new_storylines)}"
            )

            # 推进已有故事线
            for advanced_data in chapter_state.advanced_storylines:
                storyline_id = advanced_data.get("storyline_id")
                storyline_name = advanced_data.get("storyline_name")
                progress_summary = advanced_data.get("progress_summary", "")

                if storyline_id:
                    # 通过 ID 查找
                    storyline = self.storyline_repository.get_by_id(storyline_id)
                    if storyline:
                        storyline.update_progress(chapter_number, progress_summary)
                        self.storyline_repository.save(storyline)
                        logger.debug(f"Updated storyline {storyline_id}: {progress_summary[:50]}")
                    else:
                        logger.warning(f"Storyline {storyline_id} not found")
                elif storyline_name:
                    # 通过名称查找（需要遍历）
                    storylines = self.storyline_repository.get_by_novel_id(novel_id_obj)
                    found = False
                    for sl in storylines:
                        if sl.name == storyline_name:
                            sl.update_progress(chapter_number, progress_summary)
                            self.storyline_repository.save(sl)
                            logger.debug(f"Updated storyline '{storyline_name}': {progress_summary[:50]}")
                            found = True
                            break
                    if not found:
                        logger.warning(f"Storyline '{storyline_name}' not found")

            # 创建新故事线
            for new_data in chapter_state.new_storylines:
                storyline_type_str = new_data.get("type", "sub")
                # 根据类型字符串映射到枚举值
                if storyline_type_str == "main":
                    storyline_type = StorylineType.MAIN_PLOT
                else:
                    # 默认使用 GROWTH 作为支线类型
                    storyline_type = StorylineType.GROWTH

                new_storyline = Storyline(
                    id=str(uuid.uuid4()),
                    novel_id=novel_id_obj,
                    storyline_type=storyline_type,
                    status=StorylineStatus.ACTIVE,
                    estimated_chapter_start=chapter_number,
                    estimated_chapter_end=chapter_number + 50,  # 默认估计50章
                    name=new_data.get("name", ""),
                    description=new_data.get("description", ""),
                    last_active_chapter=chapter_number,
                    progress_summary=f"在第{chapter_number}章引入"
                )
                self.storyline_repository.save(new_storyline)
                logger.debug(f"Created new storyline: {new_data.get('name', '')}")

            logger.info(f"Storylines updated for novel {novel_id}")
        else:
            logger.debug("No storyline activity to update")

        # 更新 Knowledge（章节摘要）
        if self.knowledge_service:
            self._update_knowledge(novel_id, chapter_number, chapter_state)

        # 写入 chapter_elements（角色出场信息）
        if chapter_state.has_new_characters() and self.db_connection:
            self._write_chapter_elements(novel_id, chapter_number, chapter_state.new_characters)

    def _resolve_foreshadowing_id(
        self,
        registry: ForeshadowingRegistry,
        resolved_data: Dict[str, Any],
    ) -> str:
        """兼容 LLM 返回描述而非伏笔 ID 的情况。"""
        fid = str(resolved_data.get("foreshadowing_id", "")).strip()
        if fid and registry.get_by_id(fid):
            return fid

        description = str(
            resolved_data.get("description")
            or resolved_data.get("foreshadowing_description")
            or resolved_data.get("resolved_foreshadowing")
            or fid
            or ""
        ).strip()
        if not description:
            return fid

        normalized = _normalize_text(description)
        exact_match = None
        fuzzy_matches = []
        for foreshadowing in registry.foreshadowings:
            candidate = _normalize_text(foreshadowing.description)
            if not candidate:
                continue
            if candidate == normalized:
                exact_match = foreshadowing.id
                break
            if normalized in candidate or candidate in normalized:
                fuzzy_matches.append(foreshadowing.id)

        if exact_match:
            return exact_match
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0]
        if len(fuzzy_matches) > 1:
            logger.warning(
                "Ambiguous foreshadowing resolution for %r, candidates=%s",
                description,
                fuzzy_matches,
            )
            return ""
        return fid

    def _update_knowledge(
        self,
        novel_id: str,
        chapter_number: int,
        chapter_state: ChapterState
    ) -> None:
        """更新 Knowledge 中的章节摘要和知识三元组

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            chapter_state: 章节状态
        """
        try:
            # 构建关键事件描述
            events_desc = ""
            if chapter_state.events:
                event_texts = [e.get("description", "") for e in chapter_state.events[:5]]
                events_desc = "；".join(t for t in event_texts if t)

            # 构建新角色描述
            new_chars_desc = ""
            if chapter_state.new_characters:
                new_chars_desc = "新登场：" + "、".join(
                    c.get("name", "") for c in chapter_state.new_characters
                )

            key_events = events_desc or new_chars_desc or "（本章无特殊标注事件）"

            # 构建未解伏笔描述
            open_threads = ""
            if chapter_state.foreshadowing_planted:
                threads = [f.get("description", "")[:40] for f in chapter_state.foreshadowing_planted]
                open_threads = "伏笔：" + "；".join(t for t in threads if t)

            self.knowledge_service.upsert_chapter_summary(
                novel_id=novel_id,
                chapter_id=chapter_number,
                summary="",  # 暂不生成摘要文字（节省 token）
                key_events=key_events,
                open_threads=open_threads,
                consistency_note="",
                beat_sections=[],
                sync_status="auto"
            )
            logger.info(f"Knowledge chapter summary updated for novel {novel_id}, chapter {chapter_number}")

            # 如有新角色，添加为知识三元组
            for char_data in chapter_state.new_characters:
                char_name = char_data.get("name", "")
                char_desc = char_data.get("description", "")
                if char_name and char_desc:
                    fact_id = f"char-{novel_id}-{char_name}-ch{chapter_number}"
                    self.knowledge_service.upsert_fact(
                        novel_id=novel_id,
                        fact_id=fact_id,
                        subject=char_name,
                        predicate="登场于",
                        object=f"第{chapter_number}章",
                        chapter_id=chapter_number,
                        note=char_desc[:100]
                    )
        except Exception as e:
            logger.warning(f"Failed to update Knowledge for novel {novel_id}: {e}")

    def _write_chapter_elements(
        self,
        novel_id: str,
        chapter_number: int,
        new_characters: List[Dict[str, Any]]
    ) -> None:
        """写入角色出场信息到 chapter_elements 表

        Args:
            novel_id: 小说ID
            chapter_number: 章节号
            new_characters: 新角色列表
        """
        try:
            # 获取 chapter_id（需要查询 story_nodes 表）
            from domain.novel.value_objects.chapter_id import ChapterId

            # 简化实现：直接使用数据库连接查询
            # 实际项目中应该通过 chapter_repository 获取
            cursor = self.db_connection.cursor()

            # 查询章节对应的 story_node_id
            cursor.execute(
                """
                SELECT id FROM story_nodes
                WHERE novel_id = ? AND node_type = 'chapter' AND number = ?
                LIMIT 1
                """,
                (novel_id, chapter_number)
            )
            row = cursor.fetchone()

            if not row:
                logger.warning(f"Story node not found for chapter {chapter_number}")
                return

            chapter_id = row[0]

            # 批量插入角色出场记录
            inserted_count = 0
            for char_data in new_characters:
                char_name = char_data.get("name", "")
                if not char_name:
                    continue

                # 查询角色ID
                cursor.execute(
                    """
                    SELECT id FROM bible_characters
                    WHERE novel_id = ? AND name = ?
                    LIMIT 1
                    """,
                    (novel_id, char_name)
                )
                char_row = cursor.fetchone()
                char_id = char_row[0] if char_row else str(uuid.uuid4())

                # 插入 chapter_elements
                element_id = f"elem-{uuid.uuid4().hex[:8]}"

                try:
                    cursor.execute(
                        """
                        INSERT INTO chapter_elements (
                            id, chapter_id, element_type, element_id,
                            relation_type, importance, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            element_id,
                            chapter_id,
                            'character',
                            char_id,
                            'appears',
                            'normal',
                            datetime.now().isoformat()
                        )
                    )
                    inserted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to insert chapter_element for {char_name}: {e}")

            self.db_connection.commit()
            logger.info(f"Written {inserted_count} character appearances to chapter_elements")

        except Exception as e:
            logger.error(f"Failed to write chapter_elements: {e}", exc_info=True)
            if self.db_connection:
                self.db_connection.rollback()
