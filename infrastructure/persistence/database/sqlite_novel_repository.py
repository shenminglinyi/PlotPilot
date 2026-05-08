"""SQLite Novel Repository 实现"""
import logging
import json
from typing import Optional, List
from datetime import datetime
from domain.novel.entities.novel import Novel, AutopilotStatus, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteNovelRepository(NovelRepository):
    """SQLite Novel Repository 实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save(self, novel: Novel) -> None:
        """保存小说"""
        sql = """
            INSERT INTO novels (
                id, title, slug, author, target_chapters, premise,
                autopilot_status, auto_approve_mode, current_stage, current_act, current_chapter_in_act,
                max_auto_chapters, current_auto_chapters, last_chapter_tension,
                consecutive_error_count, current_beat_index, beats_completed,
                last_audit_chapter_number, last_audit_similarity, last_audit_drift_alert,
                last_audit_narrative_ok, last_audit_at,
                last_audit_vector_stored, last_audit_foreshadow_stored,
                last_audit_triples_extracted, last_audit_quality_scores, last_audit_issues,
                target_words_per_chapter, audit_progress,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                slug = excluded.slug,
                author = excluded.author,
                target_chapters = excluded.target_chapters,
                premise = excluded.premise,
                autopilot_status = excluded.autopilot_status,
                auto_approve_mode = excluded.auto_approve_mode,
                current_stage = excluded.current_stage,
                current_act = excluded.current_act,
                current_chapter_in_act = excluded.current_chapter_in_act,
                max_auto_chapters = excluded.max_auto_chapters,
                current_auto_chapters = excluded.current_auto_chapters,
                last_chapter_tension = excluded.last_chapter_tension,
                consecutive_error_count = excluded.consecutive_error_count,
                current_beat_index = excluded.current_beat_index,
                beats_completed = excluded.beats_completed,
                last_audit_chapter_number = excluded.last_audit_chapter_number,
                last_audit_similarity = excluded.last_audit_similarity,
                last_audit_drift_alert = excluded.last_audit_drift_alert,
                last_audit_narrative_ok = excluded.last_audit_narrative_ok,
                last_audit_at = excluded.last_audit_at,
                last_audit_vector_stored = excluded.last_audit_vector_stored,
                last_audit_foreshadow_stored = excluded.last_audit_foreshadow_stored,
                last_audit_triples_extracted = excluded.last_audit_triples_extracted,
                last_audit_quality_scores = excluded.last_audit_quality_scores,
                last_audit_issues = excluded.last_audit_issues,
                target_words_per_chapter = excluded.target_words_per_chapter,
                audit_progress = excluded.audit_progress,
                updated_at = excluded.updated_at
        """
        now = datetime.utcnow().isoformat()
        novel_id = novel.novel_id.value if hasattr(novel, 'novel_id') else novel.id
        slug = novel_id
        premise = getattr(novel, 'premise', '')
        author = getattr(novel, 'author', '未知作者')
        _ap = getattr(novel, 'autopilot_status', 'stopped')
        autopilot_status = _ap.value if isinstance(_ap, AutopilotStatus) else _ap
        auto_approve_mode = 1 if getattr(novel, 'auto_approve_mode', False) else 0
        _cs = getattr(novel, 'current_stage', 'planning')
        current_stage = _cs.value if isinstance(_cs, NovelStage) else _cs
        current_act = getattr(novel, 'current_act', 0)
        current_chapter_in_act = getattr(novel, 'current_chapter_in_act', 0)
        max_auto_chapters = getattr(novel, 'max_auto_chapters', 9999)
        current_auto_chapters = getattr(novel, 'current_auto_chapters', 0)
        last_chapter_tension = getattr(novel, 'last_chapter_tension', 0)
        consecutive_error_count = getattr(novel, 'consecutive_error_count', 0)
        current_beat_index = getattr(novel, 'current_beat_index', 0)
        beats_completed = 1 if getattr(novel, 'beats_completed', False) else 0
        lacn = getattr(novel, "last_audit_chapter_number", None)
        lasim = getattr(novel, "last_audit_similarity", None)
        ladr = 1 if getattr(novel, "last_audit_drift_alert", False) else 0
        lano = 1 if getattr(novel, "last_audit_narrative_ok", True) else 0
        laat = getattr(novel, "last_audit_at", None)
        # 新增字段
        lavs = 1 if getattr(novel, "last_audit_vector_stored", False) else 0
        lafs = 1 if getattr(novel, "last_audit_foreshadow_stored", False) else 0
        late = 1 if getattr(novel, "last_audit_triples_extracted", False) else 0
        laqs = getattr(novel, "last_audit_quality_scores", {})
        laqs_json = json.dumps(laqs) if laqs else None
        lai = getattr(novel, "last_audit_issues", [])
        lai_json = json.dumps(lai) if lai else None
        twpc = getattr(novel, "target_words_per_chapter", 2500)
        audit_progress = getattr(novel, "audit_progress", None)

        self.db.execute(sql, (
            novel_id,
            novel.title,
            slug,
            author,
            novel.target_chapters,
            premise,
            autopilot_status,
            auto_approve_mode,
            current_stage,
            current_act,
            current_chapter_in_act,
            max_auto_chapters,
            current_auto_chapters,
            last_chapter_tension,
            consecutive_error_count,
            current_beat_index,
            beats_completed,
            lacn,
            lasim,
            ladr,
            lano,
            laat,
            lavs,
            lafs,
            late,
            laqs_json,
            lai_json,
            twpc,
            audit_progress,
            now,
            now
        ))
        self.db.get_connection().commit()

    async def async_save(self, novel: Novel) -> None:
        """异步保存小说（守护进程使用）"""
        self.save(novel)

    def patch(self, novel_id: NovelId, **fields) -> None:
        """增量更新小说字段（只写传入的字段，减少锁竞争时间）

        适用场景：守护进程频繁更新 current_beat_index、current_stage 等少量字段时，
        无需全量 save 30+ 字段，缩短写事务持锁时间。

        Args:
            novel_id: 小说 ID
            **fields: 要更新的字段键值对，键为列名，值为目标值
                自动处理枚举类型转换（AutopilotStatus → str, NovelStage → str, bool → int）

        Examples:
            repo.patch(novel_id, current_beat_index=3, current_stage=NovelStage.WRITING)
            repo.patch(novel_id, autopilot_status=AutopilotStatus.STOPPED)
        """
        if not fields:
            return

        # 自动处理枚举类型转换
        processed = {}
        for key, value in fields.items():
            if isinstance(value, AutopilotStatus):
                processed[key] = value.value
            elif isinstance(value, NovelStage):
                processed[key] = value.value
            elif isinstance(value, bool):
                processed[key] = 1 if value else 0
            elif isinstance(value, (dict, list)):
                processed[key] = json.dumps(value)
            else:
                processed[key] = value

        # 始终更新 updated_at
        processed["updated_at"] = datetime.utcnow().isoformat()

        # 构建 UPDATE SQL
        set_clauses = [f"{key} = ?" for key in processed.keys()]
        values = list(processed.values())
        values.append(novel_id.value)

        sql = f"UPDATE novels SET {', '.join(set_clauses)} WHERE id = ?"
        self.db.execute(sql, tuple(values))
        self.db.get_connection().commit()

    def get_by_id(self, novel_id: NovelId) -> Optional[Novel]:
        """根据 ID 获取小说"""
        sql = "SELECT * FROM novels WHERE id = ?"
        row = self.db.fetch_one(sql, (novel_id.value,))

        if not row:
            return None

        return self._row_to_novel(novel_id, row)

    def get_by_slug(self, slug: str) -> Optional[Novel]:
        """根据 slug 获取小说"""
        sql = "SELECT * FROM novels WHERE slug = ?"
        row = self.db.fetch_one(sql, (slug,))

        if not row:
            return None

        return self._row_to_novel(NovelId(row['id']), row)

    def list_all(self) -> List[Novel]:
        """列出所有小说"""
        sql = "SELECT * FROM novels ORDER BY created_at DESC"
        rows = self.db.fetch_all(sql)
        return [self._row_to_novel(NovelId(row['id']), row) for row in rows]

    def find_by_autopilot_status(self, status: str) -> List[Novel]:
        """根据自动驾驶状态查找小说列表"""
        sql = "SELECT * FROM novels WHERE autopilot_status = ? ORDER BY updated_at DESC"
        rows = self.db.fetch_all(sql, (status,))
        return [self._row_to_novel(NovelId(row['id']), row) for row in rows]

    def _row_to_novel(self, novel_id: NovelId, row: dict) -> Novel:
        """将数据库行转换为 Novel 实体"""
        raw_status = row.get('autopilot_status', 'stopped')
        try:
            autopilot_status = AutopilotStatus(raw_status)
        except ValueError:
            autopilot_status = AutopilotStatus.STOPPED

        raw_stage = row.get('current_stage', 'planning')
        try:
            current_stage = NovelStage(raw_stage)
        except ValueError:
            current_stage = NovelStage.PLANNING

        _lad = row.get("last_audit_drift_alert")
        _lano = row.get("last_audit_narrative_ok")
        
        # 解析 JSON 字段
        laqs_json = row.get("last_audit_quality_scores")
        laqs = json.loads(laqs_json) if laqs_json else {}
        lai_json = row.get("last_audit_issues")
        lai = json.loads(lai_json) if lai_json else []
        
        return Novel(
            id=novel_id,
            title=row['title'],
            author=row.get('author', '未知作者'),
            target_chapters=row.get('target_chapters', 0),
            premise=row.get('premise', ''),
            autopilot_status=autopilot_status,
            auto_approve_mode=bool(row.get('auto_approve_mode', 0)),
            current_stage=current_stage,
            current_act=row.get('current_act', 0),
            current_chapter_in_act=row.get('current_chapter_in_act', 0),
            max_auto_chapters=row.get('max_auto_chapters', 9999),
            current_auto_chapters=row.get('current_auto_chapters', 0),
            last_chapter_tension=row.get('last_chapter_tension', 0),
            consecutive_error_count=row.get('consecutive_error_count', 0),
            current_beat_index=row.get('current_beat_index', 0),
            beats_completed=bool(row.get('beats_completed', 0)),
            last_audit_chapter_number=row.get("last_audit_chapter_number"),
            last_audit_similarity=row.get("last_audit_similarity"),
            last_audit_drift_alert=bool(_lad) if _lad is not None else False,
            last_audit_narrative_ok=bool(_lano) if _lano is not None else True,
            last_audit_at=row.get("last_audit_at"),
            last_audit_vector_stored=bool(row.get("last_audit_vector_stored", 0)),
            last_audit_foreshadow_stored=bool(row.get("last_audit_foreshadow_stored", 0)),
            last_audit_triples_extracted=bool(row.get("last_audit_triples_extracted", 0)),
            last_audit_quality_scores=laqs,
            last_audit_issues=lai,
            target_words_per_chapter=row.get("target_words_per_chapter", 2500),
            audit_progress=row.get("audit_progress"),
        )

    def delete(self, novel_id: NovelId) -> None:
        """删除小说（级联删除所有关联数据）"""
        sql = "DELETE FROM novels WHERE id = ?"
        self.db.execute(sql, (novel_id.value,))
        self.db.get_connection().commit()
        logger.info(f"Deleted novel: {novel_id.value}")

    def exists(self, novel_id: NovelId) -> bool:
        """检查小说是否存在"""
        sql = "SELECT 1 FROM novels WHERE id = ? LIMIT 1"
        row = self.db.fetch_one(sql, (novel_id.value,))
        return row is not None
