"""SQLite 伏笔与潜台词账本仓储。

以单行 JSON 快照持久化 ForeshadowingRegistry（与 ForeshadowingMapper 一致），
替代文件系统 foreshadowings/{novel_id}.json。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.mappers.foreshadowing_mapper import ForeshadowingMapper

logger = logging.getLogger(__name__)


class SqliteForeshadowingRepository(ForeshadowingRepository):
    """伏笔注册表 SQLite 实现。"""

    def __init__(self, db: DatabaseConnection):
        self._db = db

    def get_by_novel_id(self, novel_id: NovelId) -> Optional[ForeshadowingRegistry]:
        exists = self._db.fetch_one(
            "SELECT 1 AS o FROM novels WHERE id = ?",
            (novel_id.value,),
        )
        if not exists:
            return None

        row = self._db.fetch_one(
            "SELECT payload FROM novel_foreshadow_registry WHERE novel_id = ?",
            (novel_id.value,),
        )
        if not row:
            return ForeshadowingRegistry(
                id=f"fr-{novel_id.value}",
                novel_id=novel_id,
            )

        try:
            data = json.loads(row["payload"])
            return ForeshadowingMapper.from_dict(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                "Invalid foreshadow registry JSON for novel %s: %s",
                novel_id.value,
                e,
            )
            return ForeshadowingRegistry(
                id=f"fr-{novel_id.value}",
                novel_id=novel_id,
            )

    def save(self, registry: ForeshadowingRegistry) -> None:
        novel_row = self._db.fetch_one(
            "SELECT 1 AS o FROM novels WHERE id = ?",
            (registry.novel_id.value,),
        )
        if not novel_row:
            raise ValueError(f"Novel {registry.novel_id.value} does not exist")

        payload = json.dumps(
            ForeshadowingMapper.to_dict(registry),
            ensure_ascii=False,
        )
        now = datetime.utcnow().isoformat()
        sql = """
            INSERT INTO novel_foreshadow_registry (novel_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(novel_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
        """
        self._db.execute(sql, (registry.novel_id.value, payload, now))
        self._sync_to_foreshadows_table(registry, now)
        self._db.get_connection().commit()

    def _sync_to_foreshadows_table(self, registry: ForeshadowingRegistry, now: str) -> None:
        """将 registry 中的伏笔镜像写入 foreshadows 关系表（INSERT OR REPLACE）。"""
        novel_id = registry.novel_id.value
        try:
            for f in registry.foreshadowings:
                self._db.execute(
                    """
                    INSERT INTO foreshadows (
                        id, novel_id, description,
                        planted_chapter, due_chapter, resolved_chapter,
                        status, importance, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        description      = excluded.description,
                        planted_chapter  = excluded.planted_chapter,
                        due_chapter      = excluded.due_chapter,
                        resolved_chapter = excluded.resolved_chapter,
                        status           = excluded.status,
                        importance       = excluded.importance,
                        updated_at       = excluded.updated_at
                    """,
                    (
                        f.id,
                        novel_id,
                        f.description,
                        f.planted_in_chapter,
                        f.suggested_resolve_chapter,
                        f.resolved_in_chapter,
                        f.status.value,
                        int(f.importance),
                        now,
                    ),
                )
        except Exception as e:
            logger.warning("_sync_to_foreshadows_table failed for novel %s: %s", novel_id, e)

    # ── SQL query helpers (read from relational table) ─────────────────────

    def get_planted_sql(self, novel_id: str) -> list:
        """从 foreshadows 表查询所有 PLANTED 状态的伏笔（行字典列表）。"""
        try:
            rows = self._db.fetch_all(
                "SELECT * FROM foreshadows WHERE novel_id = ? AND status = 'planted' ORDER BY planted_chapter",
                (novel_id,),
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_planted_sql failed: %s", e)
            return []

    def get_overdue_sql(self, novel_id: str, current_chapter: int) -> list:
        """从 foreshadows 表查询已过预期解决章节但仍未解决的伏笔。"""
        try:
            rows = self._db.fetch_all(
                """
                SELECT * FROM foreshadows
                WHERE novel_id = ?
                  AND status = 'planted'
                  AND due_chapter IS NOT NULL
                  AND due_chapter <= ?
                ORDER BY importance DESC, due_chapter
                """,
                (novel_id, current_chapter),
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_overdue_sql failed: %s", e)
            return []

    def delete(self, novel_id: NovelId) -> None:
        self._db.execute(
            "DELETE FROM novel_foreshadow_registry WHERE novel_id = ?",
            (novel_id.value,),
        )
        self._db.execute(
            "DELETE FROM foreshadows WHERE novel_id = ?",
            (novel_id.value,),
        )
        self._db.get_connection().commit()
