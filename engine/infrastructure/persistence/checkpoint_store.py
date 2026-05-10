"""CheckpointStore实现 — Git式版本控制的持久化层

核心职责：
- save：保存Checkpoint（通过持久化队列异步落盘）
- load：加载Checkpoint快照
- list_story_checkpoints：列出故事的所有Checkpoint
- rollback_to：回滚到指定Checkpoint（拨回HEAD指针）
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional, Dict, Any

from engine.domain.value_objects.checkpoint import (
    Checkpoint, CheckpointId, CheckpointType,
)

logger = logging.getLogger(__name__)


class CheckpointStore:
    """Checkpoint持久化存储

    设计原则：
    - 通过持久化队列异步落盘（不阻塞写作主流程）
    - Git式树结构（parent_id）
    - HEAD指针管理（独立表）
    - 保留策略执行
    """

    def __init__(self, db_pool):
        """初始化

        Args:
            db_pool: SQLite连接池
        """
        self._db_pool = db_pool
        self._ensure_tables()

    def _ensure_tables(self):
        """确保表存在"""
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        id TEXT PRIMARY KEY,
                        story_id TEXT NOT NULL,
                        parent_id TEXT,
                        trigger_type TEXT NOT NULL,
                        trigger_reason TEXT NOT NULL DEFAULT '',
                        story_state TEXT NOT NULL DEFAULT '{}',
                        character_masks TEXT NOT NULL DEFAULT '{}',
                        emotion_ledger TEXT NOT NULL DEFAULT '{}',
                        active_foreshadows TEXT NOT NULL DEFAULT '[]',
                        outline TEXT NOT NULL DEFAULT '',
                        recent_chapters_summary TEXT NOT NULL DEFAULT '',
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_checkpoints_story_id
                    ON checkpoints(story_id, created_at DESC)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_checkpoints_parent_id
                    ON checkpoints(parent_id)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoint_heads (
                        story_id TEXT PRIMARY KEY,
                        checkpoint_id TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Checkpoint表创建失败: {e}")

    async def save(self, checkpoint: Checkpoint) -> CheckpointId:
        """保存Checkpoint

        Args:
            checkpoint: Checkpoint值对象

        Returns:
            Checkpoint ID
        """
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO checkpoints
                       (id, story_id, parent_id, trigger_type, trigger_reason,
                        story_state, character_masks, emotion_ledger,
                        active_foreshadows, outline, recent_chapters_summary, is_active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        checkpoint.checkpoint_id.value,
                        checkpoint.story_id,
                        checkpoint.parent_id.value if checkpoint.parent_id else None,
                        checkpoint.trigger_type.value,
                        checkpoint.trigger_reason,
                        json.dumps(checkpoint.story_state, ensure_ascii=False),
                        json.dumps(checkpoint.character_masks, ensure_ascii=False),
                        json.dumps(checkpoint.emotion_ledger, ensure_ascii=False),
                        json.dumps(checkpoint.active_foreshadows, ensure_ascii=False),
                        checkpoint.outline,
                        checkpoint.recent_chapters_summary,
                    )
                )
                conn.commit()
                logger.info(f"Checkpoint已保存: {checkpoint.checkpoint_id.value}")
                return checkpoint.checkpoint_id

        except Exception as e:
            logger.error(f"保存Checkpoint失败: {e}")
            raise

    async def load(self, checkpoint_id: CheckpointId) -> Optional[Checkpoint]:
        """加载Checkpoint"""
        try:
            with self._db_pool.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM checkpoints WHERE id = ? AND is_active = 1",
                    (checkpoint_id.value,)
                ).fetchone()

                if not row:
                    return None

                return self._row_to_checkpoint(dict(row))

        except Exception as e:
            logger.error(f"加载Checkpoint失败: {e}")
            return None

    async def list_story_checkpoints(
        self,
        story_id: str,
        trigger_type: Optional[CheckpointType] = None,
        limit: int = 50,
    ) -> List[Checkpoint]:
        """列出故事的所有Checkpoint"""
        try:
            with self._db_pool.get_connection() as conn:
                if trigger_type:
                    rows = conn.execute(
                        """SELECT * FROM checkpoints
                           WHERE story_id = ? AND trigger_type = ? AND is_active = 1
                           ORDER BY created_at DESC LIMIT ?""",
                        (story_id, trigger_type.value, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM checkpoints
                           WHERE story_id = ? AND is_active = 1
                           ORDER BY created_at DESC LIMIT ?""",
                        (story_id, limit)
                    ).fetchall()

                return [self._row_to_checkpoint(dict(r)) for r in rows]

        except Exception as e:
            logger.error(f"列出Checkpoint失败: {e}")
            return []

    async def get_head(self, story_id: str) -> Optional[CheckpointId]:
        """获取HEAD指针"""
        try:
            with self._db_pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT checkpoint_id FROM checkpoint_heads WHERE story_id = ?",
                    (story_id,)
                ).fetchone()

                if row:
                    return CheckpointId(row["checkpoint_id"])
                return None

        except Exception as e:
            logger.error(f"获取HEAD指针失败: {e}")
            return None

    async def set_head(self, story_id: str, checkpoint_id: CheckpointId) -> None:
        """设置HEAD指针"""
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO checkpoint_heads
                       (story_id, checkpoint_id, updated_at)
                       VALUES (?, ?, CURRENT_TIMESTAMP)""",
                    (story_id, checkpoint_id.value)
                )
                conn.commit()

        except Exception as e:
            logger.error(f"设置HEAD指针失败: {e}")

    async def rollback_to(self, story_id: str, checkpoint_id: CheckpointId) -> Optional[Checkpoint]:
        """回滚到指定Checkpoint（拨回HEAD指针）"""
        checkpoint = await self.load(checkpoint_id)
        if not checkpoint:
            logger.error(f"Checkpoint不存在: {checkpoint_id.value}")
            return None

        await self.set_head(story_id, checkpoint_id)
        logger.info(f"已回滚到Checkpoint: {checkpoint_id.value}")
        return checkpoint

    async def get_children(self, checkpoint_id: CheckpointId) -> List[Checkpoint]:
        """获取子节点（平行宇宙分支）"""
        try:
            with self._db_pool.get_connection() as conn:
                rows = conn.execute(
                    """SELECT * FROM checkpoints
                       WHERE parent_id = ? AND is_active = 1
                       ORDER BY created_at""",
                    (checkpoint_id.value,)
                ).fetchall()

                return [self._row_to_checkpoint(dict(r)) for r in rows]

        except Exception as e:
            logger.error(f"获取子节点失败: {e}")
            return []

    async def soft_delete(self, checkpoint_id: CheckpointId) -> None:
        """软删除Checkpoint（保留策略执行）"""
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    "UPDATE checkpoints SET is_active = 0 WHERE id = ?",
                    (checkpoint_id.value,)
                )
                conn.commit()

        except Exception as e:
            logger.error(f"软删除Checkpoint失败: {e}")

    def _row_to_checkpoint(self, row: Dict[str, Any]) -> Checkpoint:
        """数据库行 → Checkpoint值对象"""
        return Checkpoint(
            checkpoint_id=CheckpointId(row["id"]),
            story_id=row["story_id"],
            parent_id=CheckpointId(row["parent_id"]) if row.get("parent_id") else None,
            trigger_type=CheckpointType(row["trigger_type"]),
            trigger_reason=row.get("trigger_reason", ""),
            story_state=json.loads(row.get("story_state", "{}")),
            character_masks=json.loads(row.get("character_masks", "{}")),
            emotion_ledger=json.loads(row.get("emotion_ledger", "{}")),
            active_foreshadows=json.loads(row.get("active_foreshadows", "[]")),
            outline=row.get("outline", ""),
            recent_chapters_summary=row.get("recent_chapters_summary", ""),
            created_at=row.get("created_at", ""),
        )


# 需要导入sqlite3
import sqlite3
