"""状态启动加载器 - 从 DB 加载所有数据到共享内存

职责：
1. 应用启动时从 DB 加载所有必要数据到共享内存
2. 确保 API 进程启动后可以立即从共享内存读取
3. 提供数据恢复和一致性校验

设计原则：
- 启动时一次性加载，之后所有读取都走内存
- 加载失败不影响系统启动，返回默认值
- 支持增量加载（只加载活跃小说）
"""
import logging
import time
from typing import Any, Dict, List, Optional

from application.engine.services.shared_state_repository import (
    SharedStateRepository,
    ChapterSummary,
    NovelState,
    get_shared_state_repository,
)

logger = logging.getLogger(__name__)


class StateBootstrap:
    """状态启动加载器 - 从 DB 加载所有数据到共享内存"""

    def __init__(self, shared_state: Optional[SharedStateRepository] = None):
        self._shared = shared_state or get_shared_state_repository()

    def load_all(self) -> Dict[str, Any]:
        """加载所有小说的状态到共享内存

        Returns:
            加载统计信息
        """
        start_time = time.time()
        stats = {
            "novels_loaded": 0,
            "chapters_loaded": 0,
            "foreshadows_loaded": 0,
            "errors": [],
        }

        try:
            # 1. 加载所有小说
            novels = self._load_all_novels()
            stats["novels_loaded"] = len(novels)

            # 2. 为每个小说加载数据
            for novel in novels:
                try:
                    novel_id = novel["id"]

                    # 加载小说状态
                    self._load_novel_state(novel)

                    # 加载章节
                    chapters = self._load_chapters(novel_id)
                    stats["chapters_loaded"] += len(chapters)

                    # 加载伏笔
                    foreshadows = self._load_foreshadows(novel_id)
                    stats["foreshadows_loaded"] += len(foreshadows)

                    # 加载故事线
                    self._load_storylines(novel_id)

                    # 加载剧情弧光
                    self._load_plot_arc(novel_id)

                    # 加载 Bible
                    self._load_bible(novel_id)

                    # 加载三元组
                    self._load_triples(novel_id)

                    # 加载快照
                    self._load_snapshots(novel_id)

                    # 加载编年史（依赖 Bible + snapshots + chapters）
                    self._load_chronicles(novel_id)

                except Exception as e:
                    stats["errors"].append(f"novel {novel.get('id')}: {e}")
                    logger.error(f"加载小说数据失败: {novel.get('id')}, {e}")

        except Exception as e:
            stats["errors"].append(f"global: {e}")
            logger.error(f"加载状态失败: {e}")

        stats["elapsed_ms"] = round((time.time() - start_time) * 1000, 2)
        logger.info(f"✅ 状态加载完成: {stats}")
        return stats

    def load_novel(self, novel_id: str) -> bool:
        """加载单个小说的状态

        Args:
            novel_id: 小说 ID

        Returns:
            是否加载成功
        """
        try:
            # 加载小说基本信息
            novel = self._get_novel_by_id(novel_id)
            if not novel:
                return False

            # 加载小说状态
            self._load_novel_state(novel)

            # 加载章节
            self._load_chapters(novel_id)

            # 加载伏笔
            self._load_foreshadows(novel_id)

            # 加载故事线
            self._load_storylines(novel_id)

            # 加载剧情弧光
            self._load_plot_arc(novel_id)

            return True

        except Exception as e:
            logger.error(f"加载小说状态失败: {novel_id}, {e}")
            return False

    def _load_all_novels(self) -> List[Dict[str, Any]]:
        """从 DB 加载所有小说"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            # 🔥 needs_review 是计算字段，不存储在数据库中
            # 由 current_stage == 'paused_for_review' 推导
            rows = db.fetch_all(
                """SELECT id, title, autopilot_status, current_stage,
                          current_act, current_chapter_in_act, current_beat_index,
                          current_auto_chapters, target_chapters, target_words_per_chapter,
                          consecutive_error_count, last_chapter_tension, auto_approve_mode
                   FROM novels"""
            )

            result = []
            for row in rows:
                novel = dict(row)
                # 计算 needs_review
                novel['needs_review'] = novel.get('current_stage') == 'paused_for_review'
                result.append(novel)
            return result

        except Exception as e:
            logger.error(f"加载小说列表失败: {e}")
            return []

    def _get_novel_by_id(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """从 DB 获取单个小说"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            # 🔥 needs_review 是计算字段，不存储在数据库中
            row = db.fetch_one(
                """SELECT id, title, autopilot_status, current_stage,
                          current_act, current_chapter_in_act, current_beat_index,
                          current_auto_chapters, target_chapters, target_words_per_chapter,
                          consecutive_error_count, last_chapter_tension, auto_approve_mode
                   FROM novels WHERE id = ?""",
                (novel_id,),
            )

            if row is None:
                return None
            novel = dict(row)
            # 计算 needs_review
            novel['needs_review'] = novel.get('current_stage') == 'paused_for_review'
            return novel

        except Exception as e:
            logger.error(f"加载小说失败: {novel_id}, {e}")
            return None

    def _load_novel_state(self, novel: Dict[str, Any]) -> None:
        """加载小说状态到共享内存"""
        state = NovelState(
            novel_id=novel["id"],
            title=novel.get("title", ""),
            autopilot_status=novel.get("autopilot_status", "stopped"),
            current_stage=novel.get("current_stage", "writing"),
            current_act=novel.get("current_act"),
            current_chapter_in_act=novel.get("current_chapter_in_act"),
            current_beat_index=novel.get("current_beat_index", 0),
            current_auto_chapters=novel.get("current_auto_chapters", 0),
            target_chapters=novel.get("target_chapters", 0),
            target_words_per_chapter=novel.get("target_words_per_chapter", 2500),
            consecutive_error_count=novel.get("consecutive_error_count", 0),
            last_chapter_tension=novel.get("last_chapter_tension", 0),
            auto_approve_mode=novel.get("auto_approve_mode", False),
            needs_review=novel.get("needs_review", False),
        )

        self._shared.set_novel_state(novel["id"], state)

    def _load_chapters(self, novel_id: str) -> List[ChapterSummary]:
        """加载章节列表到共享内存"""
        try:
            from infrastructure.persistence.database.connection import get_database

            db = get_database()
            rows = db.fetch_all(
                """SELECT id, number, title, status, word_count
                   FROM chapters WHERE novel_id = ?
                   ORDER BY number""",
                (novel_id,),
            )

            chapters = []
            for row in rows:
                chapter = ChapterSummary(
                    id=row["id"],
                    number=row["number"],
                    title=row.get("title", ""),
                    status=row.get("status", "draft"),
                    word_count=row.get("word_count", 0),
                )
                chapters.append(chapter)

            self._shared.set_chapters(novel_id, chapters)
            return chapters

        except Exception as e:
            logger.error(f"加载章节失败: {novel_id}, {e}")
            return []

    def _load_foreshadows(self, novel_id: str) -> List[Dict[str, Any]]:
        """加载伏笔列表到共享内存"""
        try:
            from infrastructure.persistence.database.connection import get_database
            import json

            db = get_database()
            row = db.fetch_one(
                "SELECT payload FROM novel_foreshadow_registry WHERE novel_id = ?",
                (novel_id,),
            )

            if row:
                payload = json.loads(row["payload"])
                entries = payload.get("subtext_entries", [])
                self._shared.set_foreshadows(novel_id, entries)
                return entries

            return []

        except Exception as e:
            logger.debug(f"加载伏笔失败（可能不存在）: {novel_id}, {e}")
            return []

    def _load_storylines(self, novel_id: str) -> List[Dict[str, Any]]:
        """加载故事线列表到共享内存（含甘特图所需的 storyline_type/chapter_range/milestones 等全字段）"""
        try:
            from domain.novel.value_objects.novel_id import NovelId
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository

            repo = SqliteStorylineRepository(get_database())
            storylines = repo.get_by_novel_id(NovelId(novel_id))

            storyline_list = []
            for s in storylines:
                milestones_data = []
                if hasattr(s, 'milestones') and s.milestones:
                    for ms in s.milestones:
                        milestones_data.append({
                            "order": getattr(ms, 'order', 0),
                            "title": getattr(ms, 'title', ''),
                            "description": getattr(ms, 'description', ''),
                            "target_chapter_start": getattr(ms, 'target_chapter_start', 1),
                            "target_chapter_end": getattr(ms, 'target_chapter_end', 1),
                            "prerequisites": getattr(ms, 'prerequisites', []),
                            "triggers": getattr(ms, 'triggers', []),
                        })

                storyline_list.append({
                    "id": s.id,
                    "storyline_type": s.storyline_type.value if hasattr(s.storyline_type, "value") else str(s.storyline_type),
                    "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                    "estimated_chapter_start": getattr(s, 'estimated_chapter_start', 1),
                    "estimated_chapter_end": getattr(s, 'estimated_chapter_end', 10),
                    "name": getattr(s, 'name', ''),
                    "description": getattr(s, 'description', ''),
                    "milestones": milestones_data,
                    "current_milestone_index": getattr(s, 'current_milestone_index', 0),
                    "last_active_chapter": getattr(s, 'last_active_chapter', 0),
                    "progress_summary": getattr(s, 'progress_summary', ''),
                })

            self._shared.set_storylines(novel_id, storyline_list)
            return storyline_list

        except Exception as e:
            logger.debug(f"加载故事线失败（可能不存在）: {novel_id}, {e}")
            return []

    def _load_plot_arc(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """加载剧情弧光到共享内存"""
        try:
            from domain.novel.value_objects.novel_id import NovelId
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_plot_arc_repository import SqlitePlotArcRepository

            repo = SqlitePlotArcRepository(get_database())
            arc = repo.get_by_novel_id(NovelId(novel_id))

            if arc:
                arc_dict = {
                    "id": arc.id,
                    "novel_id": arc.novel_id.value,
                    "slug": arc.slug,
                    "display_name": arc.display_name,
                    "key_points": [
                        {
                            "chapter_number": kp.chapter_number,
                            "point_type": kp.point_type.value if hasattr(kp.point_type, 'value') else str(kp.point_type),
                            "description": kp.description,
                            "tension": kp.tension.value if hasattr(kp.tension, 'value') else str(kp.tension),
                        }
                        for kp in arc.key_points
                    ],
                }
                self._shared.set_plot_arc(novel_id, arc_dict)
                return arc_dict

            return None

        except Exception as e:
            logger.debug(f"加载剧情弧光失败（可能不存在）: {novel_id}, {e}")
            return None

    def _load_bible(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """加载 Bible 到共享内存"""
        try:
            from application.world.services.bible_service import BibleService
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository

            db = get_database()
            bible_service = BibleService(SqliteBibleRepository(db))
            bible = bible_service.get_bible_by_novel(novel_id)

            if bible:
                bible_dict = {
                    "novel_id": novel_id,
                    "title": bible.title if hasattr(bible, "title") else "",
                    "logline": bible.logline if hasattr(bible, "logline") else "",
                    "theme": bible.theme if hasattr(bible, "theme") else "",
                    "genre": bible.genre if hasattr(bible, "genre") else "",
                    "characters": [
                        {
                            "name": c.name,
                            "role": c.role if hasattr(c, "role") else "",
                            "description": c.description if hasattr(c, "description") else "",
                        }
                        for c in (bible.characters or [])
                    ] if hasattr(bible, "characters") else [],
                    "timeline_notes": [
                        {
                            "id": n.id,
                            "time_point": n.time_point,
                            "event": n.event,
                            "description": n.description,
                        }
                        for n in (bible.timeline_notes or [])
                    ] if hasattr(bible, "timeline_notes") else [],
                }
                self._shared.set_bible(novel_id, bible_dict)
                return bible_dict

            return None

        except Exception as e:
            logger.debug(f"加载 Bible 失败（可能不存在）: {novel_id}, {e}")
            return None

    def _load_triples(self, novel_id: str) -> List[Dict[str, Any]]:
        """加载三元组到共享内存"""
        try:
            from infrastructure.persistence.database.triple_repository import TripleRepository
            import asyncio

            repo = TripleRepository()

            # 同步调用异步方法
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                # 如果事件循环正在运行，创建一个新的
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        repo.get_by_novel(novel_id)
                    )
                    triples = future.result(timeout=5)
            else:
                triples = loop.run_until_complete(repo.get_by_novel(novel_id))

            triples_list = [
                {
                    "id": t.id,
                    "subject_type": t.subject_type,
                    "subject_id": t.subject_id,
                    "predicate": t.predicate,
                    "object_type": t.object_type,
                    "object_id": t.object_id,
                    "source_type": t.source_type.value if hasattr(t.source_type, "value") else str(t.source_type),
                }
                for t in (triples or [])
            ]

            self._shared.set_triples(novel_id, triples_list)
            return triples_list

        except Exception as e:
            logger.debug(f"加载三元组失败（可能不存在）: {novel_id}, {e}")
            return []

    def _load_snapshots(self, novel_id: str) -> List[Dict[str, Any]]:
        """加载快照到共享内存"""
        try:
            from application.snapshot.services.snapshot_service import SnapshotService
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository

            db = get_database()
            chapter_repo = SqliteChapterRepository(db)
            snapshot_service = SnapshotService(db, chapter_repo)
            snapshots_raw = snapshot_service.list_snapshots_with_pointers(novel_id)

            snapshots_list = [
                {
                    "id": s.get("id"),
                    "chapter_number": s.get("chapter_number"),
                    "title": s.get("title", ""),
                    "story_events": s.get("story_events", []),
                    # 🔥 补全编年史聚合所需的字段
                    "name": s.get("name", ""),
                    "trigger_type": s.get("trigger_type", "AUTO"),
                    "branch_name": s.get("branch_name", "main"),
                    "created_at": s.get("created_at"),
                    "description": s.get("description"),
                    "chapter_pointers": s.get("chapter_pointers", []),
                }
                for s in (snapshots_raw or [])
            ]

            self._shared.set_snapshots(novel_id, snapshots_list)
            return snapshots_list

        except Exception as e:
            logger.debug(f"加载快照失败（可能不存在）: {novel_id}, {e}")
            return []

    def _load_chronicles(self, novel_id: str) -> List[Dict[str, Any]]:
        """从共享内存已有的 Bible timeline_notes + snapshots + chapters 实时聚合编年史，写入共享内存缓存。

        必须在 _load_bible / _load_snapshots / _load_chapters 之后调用。
        """
        try:
            from application.codex.chronicles_service import build_chronicles_rows

            bible = self._shared.get_bible(novel_id) or {}
            snapshots_raw = self._shared.get_snapshots(novel_id) or []
            chapters = self._shared.get_chapters(novel_id)

            # 构建 chapter_id → chapter_number 映射
            id_to_number: Dict[str, int] = {}
            for c in chapters:
                if c.id and c.number:
                    id_to_number[c.id] = c.number

            # 提取 Bible timeline_notes
            timeline_notes = bible.get("timeline_notes", []) if isinstance(bible, dict) else []

            # 将 timeline_notes 转为 build_chronicles_rows 所需的元组格式
            note_tuples = []
            for n in timeline_notes:
                if isinstance(n, dict):
                    note_tuples.append((
                        n.get("id", ""),
                        n.get("time_point", "") or n.get("time", ""),
                        n.get("event", "") or n.get("title", ""),
                        n.get("description", ""),
                    ))

            rows = build_chronicles_rows(note_tuples, snapshots_raw, id_to_number)

            self._shared.set_chronicles(novel_id, rows)
            return rows

        except Exception as e:
            logger.debug(f"加载编年史失败（可能 Bible/snapshots 不存在）: {novel_id}, {e}")
            return []


def bootstrap_state() -> Dict[str, Any]:
    """启动时加载所有状态（便捷函数）"""
    bootstrap = StateBootstrap()
    return bootstrap.load_all()


def bootstrap_novel(novel_id: str) -> bool:
    """加载单个小说状态（便捷函数）"""
    bootstrap = StateBootstrap()
    return bootstrap.load_novel(novel_id)
