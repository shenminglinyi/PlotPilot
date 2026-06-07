"""
Repository for Worldbuilding
"""
import json
from typing import Optional
from datetime import datetime

from domain.worldbuilding.worldbuilding import Worldbuilding


class WorldbuildingRepository:
    """世界观构建仓储"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        """确保表存在"""
        from infrastructure.persistence.database.connection import get_database

        db = get_database(self.db_path)
        db.execute("""
                CREATE TABLE IF NOT EXISTS worldbuilding (
                    id TEXT PRIMARY KEY,
                    novel_id TEXT NOT NULL UNIQUE,

                    power_system TEXT DEFAULT '',
                    physics_rules TEXT DEFAULT '',
                    magic_tech TEXT DEFAULT '',

                    terrain TEXT DEFAULT '',
                    climate TEXT DEFAULT '',
                    resources TEXT DEFAULT '',
                    ecology TEXT DEFAULT '',

                    politics TEXT DEFAULT '',
                    economy TEXT DEFAULT '',
                    class_system TEXT DEFAULT '',

                    history TEXT DEFAULT '',
                    religion TEXT DEFAULT '',
                    taboos TEXT DEFAULT '',

                    food_clothing TEXT DEFAULT '',
                    language_slang TEXT DEFAULT '',
                    entertainment TEXT DEFAULT '',

                    schema_version INTEGER NOT NULL DEFAULT 1,
                    dimensions TEXT NOT NULL DEFAULT '{}',

                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
                )
            """)
        self._ensure_v2_columns(db)
        db.commit()

    def _ensure_v2_columns(self, db) -> None:
        cur = db.execute("PRAGMA table_info(worldbuilding)")
        cols = {row[1] for row in cur.fetchall()}
        if "schema_version" not in cols:
            db.execute("ALTER TABLE worldbuilding ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1")
        if "dimensions" not in cols:
            db.execute("ALTER TABLE worldbuilding ADD COLUMN dimensions TEXT NOT NULL DEFAULT '{}'")

    def get_by_novel_id(self, novel_id: str) -> Optional[Worldbuilding]:
        """根据小说ID获取世界观"""
        from infrastructure.persistence.database.connection import get_database

        db = get_database(self.db_path)
        row = db.fetch_one(
            "SELECT * FROM worldbuilding WHERE novel_id = ?",
            (novel_id,),
        )

        if not row:
            return None

        dimensions = self._parse_dimensions(row["dimensions"] if "dimensions" in row.keys() else None)
        schema_version = int(row["schema_version"] or 1) if "schema_version" in row.keys() else 1

        return Worldbuilding(
            id=row["id"],
            novel_id=row["novel_id"],
            power_system=row["power_system"] or "",
            physics_rules=row["physics_rules"] or "",
            magic_tech=row["magic_tech"] or "",
            terrain=row["terrain"] or "",
            climate=row["climate"] or "",
            resources=row["resources"] or "",
            ecology=row["ecology"] or "",
            politics=row["politics"] or "",
            economy=row["economy"] or "",
            class_system=row["class_system"] or "",
            history=row["history"] or "",
            religion=row["religion"] or "",
            taboos=row["taboos"] or "",
            food_clothing=row["food_clothing"] or "",
            language_slang=row["language_slang"] or "",
            entertainment=row["entertainment"] or "",
            schema_version=schema_version,
            dimensions=dimensions,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _parse_dimensions(self, raw: Optional[str]) -> dict:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(parsed, dict):
            return {}
        out = {}
        for dim, block in parsed.items():
            if not isinstance(block, dict):
                continue
            fields = {
                str(k): str(v or "")
                for k, v in block.items()
                if str(v or "").strip()
            }
            if fields:
                out[str(dim)] = fields
        return out

    def save(self, worldbuilding: Worldbuilding) -> None:
        """保存世界观"""
        from infrastructure.persistence.database.connection import get_database

        db = get_database(self.db_path)
        dimensions = worldbuilding.normalized_dimensions()
        db.execute(
            """
                INSERT OR REPLACE INTO worldbuilding (
                    id, novel_id,
                    power_system, physics_rules, magic_tech,
                    terrain, climate, resources, ecology,
                    politics, economy, class_system,
                    history, religion, taboos,
                    food_clothing, language_slang, entertainment,
                    schema_version, dimensions,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worldbuilding.id,
                worldbuilding.novel_id,
                worldbuilding.power_system,
                worldbuilding.physics_rules,
                worldbuilding.magic_tech,
                worldbuilding.terrain,
                worldbuilding.climate,
                worldbuilding.resources,
                worldbuilding.ecology,
                worldbuilding.politics,
                worldbuilding.economy,
                worldbuilding.class_system,
                worldbuilding.history,
                worldbuilding.religion,
                worldbuilding.taboos,
                worldbuilding.food_clothing,
                worldbuilding.language_slang,
                worldbuilding.entertainment,
                int(worldbuilding.schema_version or 2),
                json.dumps(dimensions, ensure_ascii=False),
                worldbuilding.created_at.isoformat() if isinstance(worldbuilding.created_at, datetime) else worldbuilding.created_at,
                datetime.now().isoformat(),
            ),
        )
        db.commit()

    def delete_by_novel_id(self, novel_id: str) -> None:
        """删除小说的世界观"""
        from infrastructure.persistence.database.connection import get_database

        db = get_database(self.db_path)
        db.execute("DELETE FROM worldbuilding WHERE novel_id = ?", (novel_id,))
        db.commit()
