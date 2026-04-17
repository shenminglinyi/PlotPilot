"""SQLite Custom Theme Skill Repository

用户自定义增强技能的持久化存储。
每个自定义技能归属于某个 novel，用户在前端填写提示词内容，
运行时被包装为 ThemeSkill 实例注入管线。
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteCustomSkillRepository:
    """用户自定义增强技能仓储"""

    def __init__(self, db: DatabaseConnection):
        self.db = db
        self._ensure_table()

    def _ensure_table(self) -> None:
        """确保表存在（兼容旧数据库）"""
        sql = """
            CREATE TABLE IF NOT EXISTS custom_theme_skills (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                skill_key TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                skill_description TEXT DEFAULT '',
                compatible_genres TEXT DEFAULT '[]',
                context_prompt TEXT DEFAULT '',
                beat_prompt TEXT DEFAULT '',
                beat_triggers TEXT DEFAULT '',
                audit_checks TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_id, skill_key)
            )
        """
        self.db.execute(sql)
        self.db.get_connection().commit()

    def save(self, skill_data: Dict[str, Any]) -> None:
        """保存自定义技能（UPSERT）

        Args:
            skill_data: 技能数据字典，包含:
                - id: 技能 ID
                - novel_id: 小说 ID
                - skill_key: 技能唯一标识
                - skill_name: 技能名称
                - skill_description: 技能描述
                - compatible_genres: 适用题材列表
                - context_prompt: 上下文增强提示词
                - beat_prompt: 节拍增强提示词
                - beat_triggers: 触发关键词（逗号分隔）
                - audit_checks: 审计检查项列表
        """
        now = datetime.utcnow().isoformat()
        sql = """
            INSERT INTO custom_theme_skills (
                id, novel_id, skill_key, skill_name, skill_description,
                compatible_genres, context_prompt, beat_prompt, beat_triggers,
                audit_checks, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                skill_key = excluded.skill_key,
                skill_name = excluded.skill_name,
                skill_description = excluded.skill_description,
                compatible_genres = excluded.compatible_genres,
                context_prompt = excluded.context_prompt,
                beat_prompt = excluded.beat_prompt,
                beat_triggers = excluded.beat_triggers,
                audit_checks = excluded.audit_checks,
                updated_at = excluded.updated_at
        """
        genres = skill_data.get("compatible_genres", [])
        audit = skill_data.get("audit_checks", [])

        self.db.execute(sql, (
            skill_data["id"],
            skill_data["novel_id"],
            skill_data["skill_key"],
            skill_data["skill_name"],
            skill_data.get("skill_description", ""),
            json.dumps(genres, ensure_ascii=False) if isinstance(genres, list) else genres,
            skill_data.get("context_prompt", ""),
            skill_data.get("beat_prompt", ""),
            skill_data.get("beat_triggers", ""),
            json.dumps(audit, ensure_ascii=False) if isinstance(audit, list) else audit,
            now,
            now,
        ))
        self.db.get_connection().commit()

    def list_by_novel(self, novel_id: str) -> List[Dict[str, Any]]:
        """列出小说的所有自定义技能"""
        sql = "SELECT * FROM custom_theme_skills WHERE novel_id = ? ORDER BY created_at"
        rows = self.db.fetch_all(sql, (novel_id,))
        return [self._row_to_dict(row) for row in rows]

    def get_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取技能"""
        sql = "SELECT * FROM custom_theme_skills WHERE id = ?"
        row = self.db.fetch_one(sql, (skill_id,))
        return self._row_to_dict(row) if row else None

    def delete(self, skill_id: str) -> bool:
        """删除技能"""
        sql = "DELETE FROM custom_theme_skills WHERE id = ?"
        self.db.execute(sql, (skill_id,))
        self.db.get_connection().commit()
        return True

    def _row_to_dict(self, row: dict) -> Dict[str, Any]:
        """行 → 字典"""
        genres_raw = row.get("compatible_genres", "[]")
        audit_raw = row.get("audit_checks", "[]")
        return {
            "id": row["id"],
            "novel_id": row["novel_id"],
            "skill_key": row["skill_key"],
            "skill_name": row["skill_name"],
            "skill_description": row.get("skill_description", ""),
            "compatible_genres": json.loads(genres_raw) if genres_raw else [],
            "context_prompt": row.get("context_prompt", ""),
            "beat_prompt": row.get("beat_prompt", ""),
            "beat_triggers": row.get("beat_triggers", ""),
            "audit_checks": json.loads(audit_raw) if audit_raw else [],
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
