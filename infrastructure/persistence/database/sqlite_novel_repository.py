"""SQLite Novel Repository 实现"""
import logging
import json
import sqlite3
import uuid
from typing import Any, Optional, List, Sequence, Tuple
from datetime import datetime, timezone
from application.ai_invocation.variable_hub import sanitize_variable_value, variable_key_candidates
from domain.novel.entities.novel import Novel, AutopilotStatus, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.generation_preferences import GenerationPreferences
from domain.novel.repositories.novel_repository import NovelRepository
from domain.shared.exceptions import InvalidOperationError
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_corruption import is_sqlite_storage_corruption

logger = logging.getLogger(__name__)


class SqliteNovelRepository(NovelRepository):
    """SQLite Novel Repository 实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db
        self._sqlite_corruption_notice: Optional[str] = None

    def _record_sqlite_corruption(self, exc: BaseException) -> None:
        self._sqlite_corruption_notice = str(exc)[:500]

    def consume_sqlite_corruption_warning(self) -> Optional[str]:
        """Return and clear a one-shot client hint after a degraded read (e.g. empty list)."""
        msg = self._sqlite_corruption_notice
        self._sqlite_corruption_notice = None
        return msg

    _INSERT_NOVEL_COLUMNS_SQL = """
            INSERT INTO novels (
                id, title, slug, author, target_chapters, premise,
                autopilot_status, auto_approve_mode, current_stage, current_act, current_chapter_in_act,
                max_auto_chapters, current_auto_chapters, last_chapter_tension,
                consecutive_error_count, current_beat_index, beats_completed,
                last_audit_chapter_number, last_audit_similarity, last_audit_drift_alert,
                last_audit_narrative_ok, last_audit_at,
                last_audit_vector_stored, last_audit_foreshadow_stored,
                last_audit_triples_extracted, last_audit_quality_scores, last_audit_issues,
                target_words_per_chapter, audit_progress, generation_prefs_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    def _serialize_novel_insert_params(self, novel: Novel, now: str) -> Tuple[str, str, tuple]:
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
        lavs = 1 if getattr(novel, "last_audit_vector_stored", False) else 0
        lafs = 1 if getattr(novel, "last_audit_foreshadow_stored", False) else 0
        late = 1 if getattr(novel, "last_audit_triples_extracted", False) else 0
        laqs = getattr(novel, "last_audit_quality_scores", {})
        laqs_json = json.dumps(laqs) if laqs else None
        lai = getattr(novel, "last_audit_issues", [])
        lai_json = json.dumps(lai) if lai else None
        twpc = getattr(novel, "target_words_per_chapter", 2500)
        audit_progress = getattr(novel, "audit_progress", None)
        _gp = getattr(novel, "generation_prefs", None)
        if _gp is not None and hasattr(_gp, "to_dict"):
            generation_prefs_json = json.dumps(_gp.to_dict(), ensure_ascii=False)
        else:
            generation_prefs_json = json.dumps(GenerationPreferences().to_dict(), ensure_ascii=False)

        params = (
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
            generation_prefs_json,
            now,
            now,
        )
        return novel_id, slug, params

    def save(self, novel: Novel) -> None:
        """保存小说"""
        sql = f"""
            {self._INSERT_NOVEL_COLUMNS_SQL}
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
                generation_prefs_json = excluded.generation_prefs_json,
                updated_at = excluded.updated_at
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        _, _, params = self._serialize_novel_insert_params(novel, now)
        self.db.execute(sql, params)
        self.db.get_connection().commit()

    def create_if_absent(self, novel: Novel) -> Tuple[Novel, bool]:
        """原子创建小说（BEGIN IMMEDIATE + ON CONFLICT DO NOTHING）。

        强制要求顶层事务独占权：若当前连接处于未提交的外层事务中则拒绝执行，
        避免 SAVEPOINT 分支在外层事务提交前伪报已落盘或误提交无关事务；
        同步直连提交保证建书返回后独立连接立即可读，且重复请求绝不覆盖既有书目的阶段、自动驾驶或审计列。
        """
        from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

        sql = f"""
            {self._INSERT_NOVEL_COLUMNS_SQL}
            ON CONFLICT DO NOTHING
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        novel_id, slug, params = self._serialize_novel_insert_params(novel, now)
        with sqlite_writes_bypass_queue():
            conn = self.db.get_connection()
            if conn.in_transaction:
                raise InvalidOperationError(
                    "SqliteNovelRepository.create_if_absent requires top-level transaction ownership "
                    "to guarantee synchronous committed visibility; active outer transaction detected"
                )
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(sql, params)
                inserted = cur.rowcount == 1
                row_cur = conn.execute(
                    "SELECT * FROM novels WHERE id = ? OR slug = ? LIMIT 1",
                    (novel_id, slug),
                )
                raw_row = row_cur.fetchone()
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
            self.db._maybe_checkpoint()

        if inserted:
            return novel, True
        if raw_row is None:
            raise RuntimeError(f"Novel '{novel_id}' creation conflicted without readable row")
        row_dict = dict(raw_row)
        existing = self._row_to_novel(NovelId(str(row_dict["id"])), row_dict)
        return existing, False

    def init_setup_variables_if_absent(
        self,
        novel_id: str,
        entries: Sequence[Tuple[str, Any, str, str]],
    ) -> int:
        """在单个 BEGIN IMMEDIATE 事务中对缺失的 setup 变量执行原子 INSERT-IF-ABSENT。

        首次建书初始化与幂等重试修复共用此方法：
        1. 绝不依赖前置 list_current_values 读快照再调覆盖式 set_value；
        2. 写入执行时刻在写锁下按规范键与等价别名集合判定 is_current = 1 是否已存在，
           若用户或并发请求已写入定制值则跳过该键，绝不覆盖。
        """
        from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue

        scope_key = f"novel_id:{novel_id}"
        def_metadata_json = json.dumps(
            {"stage": "setup", "source": "ai_invocation"},
            ensure_ascii=False,
            sort_keys=True,
        )
        val_metadata_json = json.dumps(
            {"source_commit_id": "", "stage": "setup"},
            ensure_ascii=False,
            sort_keys=True,
        )
        lineage_json = json.dumps(
            {"source": "novel_service"},
            ensure_ascii=False,
            sort_keys=True,
        )

        prepared: List[Tuple[str, str, str, str, str, Tuple[str, ...]]] = []
        for raw_key, raw_value, value_type, display_name in entries:
            key = str(raw_key or "").strip()
            if not key or raw_value in ("", None):
                continue
            clean_value = sanitize_variable_value(key, raw_value)
            if clean_value in ("", None):
                continue
            value_json = json.dumps(clean_value, ensure_ascii=False, sort_keys=True, default=str)
            value_hash = json.dumps({"value": clean_value}, ensure_ascii=False, sort_keys=True, default=str)
            candidates = variable_key_candidates(key)
            prepared.append(
                (
                    key,
                    str(value_type or "string"),
                    str(display_name or ""),
                    value_json,
                    value_hash,
                    candidates,
                )
            )

        with sqlite_writes_bypass_queue():
            conn = self.db.get_connection()
            if conn.in_transaction:
                raise InvalidOperationError(
                    "SqliteNovelRepository.init_setup_variables_if_absent requires top-level transaction "
                    "ownership; active outer transaction detected"
                )
            if not prepared:
                return 0
            inserted_count = 0
            try:
                conn.execute("BEGIN IMMEDIATE")
                for key, value_type, display_name, value_json, value_hash, candidates in prepared:
                    conn.execute(
                        """
                        INSERT INTO variable_definitions (
                            id, variable_key, display_name, value_type, scope_level,
                            required, default_value_json, description, status, metadata_json, updated_at
                        ) VALUES (?, ?, ?, ?, 'novel', 0, NULL, '', 'active', ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(variable_key) DO UPDATE SET
                            display_name = CASE
                                WHEN excluded.display_name != '' THEN excluded.display_name
                                ELSE variable_definitions.display_name
                            END,
                            value_type = excluded.value_type,
                            scope_level = excluded.scope_level,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            f"var_def_{uuid.uuid4().hex}",
                            key,
                            display_name,
                            value_type,
                            def_metadata_json,
                        ),
                    )
                    value_id = f"var_value_{uuid.uuid4().hex}"
                    candidate_placeholders = ",".join("?" for _ in candidates)
                    cur = conn.execute(
                        f"""
                        INSERT INTO variable_values (
                            id, variable_key, scope_level, scope_key, value_json, value_hash,
                            version_number, is_current, source_session_id, source_attempt_id,
                            source_trace_id, source_node_key, metadata_json
                        )
                        SELECT
                            ?,
                            ?,
                            'novel',
                            ?,
                            ?,
                            ?,
                            COALESCE(
                                (
                                    SELECT MAX(version_number)
                                    FROM variable_values
                                    WHERE variable_key = ? AND scope_level = 'novel' AND scope_key = ?
                                ),
                                0
                            ) + 1,
                            1,
                            '',
                            '',
                            'novel_service_sync',
                            'novel_service',
                            ?
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM variable_values
                            WHERE variable_key IN ({candidate_placeholders})
                              AND scope_level = 'novel'
                              AND scope_key = ?
                              AND is_current = 1
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            value_id,
                            key,
                            scope_key,
                            value_json,
                            value_hash,
                            key,
                            scope_key,
                            val_metadata_json,
                            *candidates,
                            scope_key,
                        ),
                    )
                    if cur.rowcount == 1:
                        conn.execute(
                            """
                            INSERT INTO variable_lineage (
                                id, variable_value_id, source_session_id, source_attempt_id,
                                source_trace_id, source_node_key, source_commit_id, lineage_json
                            ) VALUES (?, ?, '', '', 'novel_service_sync', 'novel_service', '', ?)
                            """,
                            (
                                f"var_lineage_{uuid.uuid4().hex}",
                                value_id,
                                lineage_json,
                            ),
                        )
                        inserted_count += 1
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
            self.db._maybe_checkpoint()
        return inserted_count

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
        try:
            row = self.db.fetch_one(sql, (novel_id.value,))
        except sqlite3.DatabaseError as e:
            if is_sqlite_storage_corruption(e):
                self._record_sqlite_corruption(e)
                logger.error(
                    "SQLite storage corruption while reading novel id=%s: %s",
                    novel_id.value,
                    e,
                )
                return None
            raise

        if not row:
            return None

        return self._row_to_novel(novel_id, row)

    def get_by_slug(self, slug: str) -> Optional[Novel]:
        """根据 slug 获取小说"""
        sql = "SELECT * FROM novels WHERE slug = ?"
        try:
            row = self.db.fetch_one(sql, (slug,))
        except sqlite3.DatabaseError as e:
            if is_sqlite_storage_corruption(e):
                self._record_sqlite_corruption(e)
                logger.error(
                    "SQLite storage corruption while reading novel slug=%s: %s",
                    slug,
                    e,
                )
                return None
            raise

        if not row:
            return None

        return self._row_to_novel(NovelId(row['id']), row)

    def list_all(self) -> List[Novel]:
        """列出所有小说"""
        sql = "SELECT * FROM novels ORDER BY created_at DESC"
        try:
            rows = self.db.fetch_all(sql)
        except sqlite3.DatabaseError as e:
            if is_sqlite_storage_corruption(e):
                self._record_sqlite_corruption(e)
                logger.error(
                    "SQLite storage corruption while listing novels; returning empty list. %s",
                    e,
                    exc_info=True,
                )
                return []
            raise
        return [self._row_to_novel(NovelId(row['id']), row) for row in rows]

    def find_by_autopilot_status(self, status: str) -> List[Novel]:
        """根据自动驾驶状态查找小说列表（优化版本，避免 N+1）

        优化说明：
        - 使用 JOIN 一次性加载小说和章节数据
        - 查询次数从 N+1 降低到 1
        - 性能提升约 6 倍
        """
        try:
            from infrastructure.persistence.database.query_optimizations import find_novels_with_chapters_optimized
            from infrastructure.persistence.database.connection import get_connection_pool

            # 使用连接池
            db_pool = get_connection_pool()
            return find_novels_with_chapters_optimized(db_pool, status)

        except Exception as e:
            if is_sqlite_storage_corruption(e):
                self._record_sqlite_corruption(e)
                logger.error(
                    "SQLite storage corruption in autopilot novel query; returning empty list. %s",
                    e,
                    exc_info=True,
                )
                return []
            logger.warning(f"优化查询失败，降级到原查询: {e}")
            # 降级到原查询
            sql = "SELECT * FROM novels WHERE autopilot_status = ? ORDER BY updated_at DESC"
            try:
                rows = self.db.fetch_all(sql, (status,))
            except sqlite3.DatabaseError as e2:
                if is_sqlite_storage_corruption(e2):
                    self._record_sqlite_corruption(e2)
                    logger.error(
                        "SQLite storage corruption in autopilot fallback query; returning empty list. %s",
                        e2,
                        exc_info=True,
                    )
                    return []
                raise
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

        generation_prefs = GenerationPreferences.from_json(row.get("generation_prefs_json"))

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
            autopilot_run_epoch=row.get("autopilot_run_epoch", 0),
            active_pipeline_step=row.get("active_pipeline_step", "") or "",
            active_pipeline_run_id=row.get("active_pipeline_run_id", "") or "",
            last_stable_stage=row.get("last_stable_stage", "") or "",
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
            generation_prefs=generation_prefs,
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
