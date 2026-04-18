"""SQLite 伏笔与潜台词账本仓储�?

以单�?JSON 快照持久�?ForeshadowingRegistry（与 ForeshadowingMapper 一致）�?
替代文件系统 foreshadowings/{novel_id}.json�?
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.mappers.foreshadowing_mapper import ForeshadowingMapper

logger = logging.getLogger(__name__)


class SqliteForeshadowingRepository(ForeshadowingRepository):
    """伏笔注册�?SQLite 实现�?""

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
        now = datetime.now(timezone.utc).isoformat()
        sql = """
            INSERT INTO novel_foreshadow_registry (novel_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(novel_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
        """
        self._db.execute(sql, (registry.novel_id.value, payload, now))
        self._db.get_connection().commit()

    def delete(self, novel_id: NovelId) -> None:
        self._db.execute(
            "DELETE FROM novel_foreshadow_registry WHERE novel_id = ?",
            (novel_id.value,),
        )
        self._db.get_connection().commit()
