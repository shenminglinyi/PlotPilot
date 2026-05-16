"""CheckpointManager — 应用层Checkpoint管理

触发策略（A+C混合方案）：
- 章节完成 → CHAPTER（保留最近10章）
- 幕切换 → ACT（永久保留）
- 大纲变更 → MILESTONE（保留最近5个）
- 用户干预 → MANUAL（保留24小时）

保留策略：
- ACT类型：永久保留
- CHAPTER类型：保留最近10个
- MILESTONE类型：保留最近5个
- MANUAL类型：保留24小时
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from engine.core.entities.story import StoryId, StoryPhase
from engine.core.value_objects.checkpoint import (
    Checkpoint, CheckpointId, CheckpointType, RETENTION_POLICY,
)
from engine.infrastructure.persistence.checkpoint_store import CheckpointStore

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Checkpoint管理器（应用层）

    核心职责：
    - 判断何时触发Checkpoint
    - 执行保留策略
    - HEAD指针管理
    - 与StoryEngine集成
    """

    def __init__(self, checkpoint_store: CheckpointStore):
        self._store = checkpoint_store

    async def on_chapter_completed(
        self,
        story_id: str,
        chapter_number: int,
        story_state: Dict[str, Any],
        character_masks: Dict[str, Any],
        emotion_ledger: Dict[str, Any],
        active_foreshadows: List[str],
        outline: str = "",
        recent_summary: str = "",
    ) -> CheckpointId:
        """章节完成触发Checkpoint

        Args:
            story_id: 故事ID
            chapter_number: 章节号
            story_state: 故事状态快照
            character_masks: 角色面具快照
            emotion_ledger: 情绪账本快照
            active_foreshadows: 活跃伏笔列表
            outline: 当前大纲
            recent_summary: 近期摘要

        Returns:
            Checkpoint ID
        """
        # 获取当前HEAD
        parent_id = await self._store.get_head(story_id)

        checkpoint = Checkpoint.create(
            story_id=story_id,
            trigger_type=CheckpointType.CHAPTER,
            trigger_reason=f"第{chapter_number}章完成",
            story_state=story_state,
            character_masks=character_masks,
            emotion_ledger=emotion_ledger,
            active_foreshadows=active_foreshadows,
            parent_id=parent_id,
            outline=outline,
            recent_chapters_summary=recent_summary,
        )

        # 保存
        checkpoint_id = await self._store.save(checkpoint)

        # 更新HEAD
        await self._store.set_head(story_id, checkpoint_id)

        # 执行保留策略
        await self._enforce_retention(story_id, CheckpointType.CHAPTER)

        logger.info(f"✅ 第{chapter_number}章Checkpoint已创建: {checkpoint_id.value}")
        return checkpoint_id

    async def on_act_transition(
        self,
        story_id: str,
        from_phase: StoryPhase,
        to_phase: StoryPhase,
        story_state: Dict[str, Any],
        character_masks: Dict[str, Any],
        emotion_ledger: Dict[str, Any],
        active_foreshadows: List[str],
        outline: str = "",
    ) -> CheckpointId:
        """幕切换触发Checkpoint（永久保留）"""
        parent_id = await self._store.get_head(story_id)

        checkpoint = Checkpoint.create(
            story_id=story_id,
            trigger_type=CheckpointType.ACT,
            trigger_reason=f"幕切换: {from_phase.value} → {to_phase.value}",
            story_state=story_state,
            character_masks=character_masks,
            emotion_ledger=emotion_ledger,
            active_foreshadows=active_foreshadows,
            parent_id=parent_id,
            outline=outline,
        )

        checkpoint_id = await self._store.save(checkpoint)
        await self._store.set_head(story_id, checkpoint_id)

        # ACT类型永久保留，不需要执行保留策略
        logger.info(f"🌟 幕切换Checkpoint已创建（永久保留）: {checkpoint_id.value}")
        return checkpoint_id

    async def on_outline_change(
        self,
        story_id: str,
        change_description: str,
        story_state: Dict[str, Any],
        character_masks: Dict[str, Any],
        emotion_ledger: Dict[str, Any],
        active_foreshadows: List[str],
        outline: str = "",
    ) -> CheckpointId:
        """大纲变更触发Checkpoint"""
        parent_id = await self._store.get_head(story_id)

        checkpoint = Checkpoint.create(
            story_id=story_id,
            trigger_type=CheckpointType.MILESTONE,
            trigger_reason=f"大纲变更: {change_description}",
            story_state=story_state,
            character_masks=character_masks,
            emotion_ledger=emotion_ledger,
            active_foreshadows=active_foreshadows,
            parent_id=parent_id,
            outline=outline,
        )

        checkpoint_id = await self._store.save(checkpoint)
        await self._store.set_head(story_id, checkpoint_id)

        await self._enforce_retention(story_id, CheckpointType.MILESTONE)

        logger.info(f"📌 大纲变更Checkpoint已创建: {checkpoint_id.value}")
        return checkpoint_id

    async def rollback(self, story_id: str, checkpoint_id: CheckpointId) -> Optional[Checkpoint]:
        """回滚到指定Checkpoint"""
        checkpoint = await self._store.rollback_to(story_id, checkpoint_id)
        if checkpoint:
            logger.info(f"⏪ 已回滚到Checkpoint: {checkpoint_id.value}")
        return checkpoint

    async def get_current_state(self, story_id: str) -> Optional[Dict[str, Any]]:
        """获取当前Checkpoint的完整状态"""
        head_id = await self._store.get_head(story_id)
        if not head_id:
            return None

        checkpoint = await self._store.load(head_id)
        if not checkpoint:
            return None

        return {
            "checkpoint_id": checkpoint.checkpoint_id.value,
            "story_state": checkpoint.story_state,
            "character_masks": checkpoint.character_masks,
            "emotion_ledger": checkpoint.emotion_ledger,
            "active_foreshadows": checkpoint.active_foreshadows,
            "outline": checkpoint.outline,
        }

    async def list_branches(self, story_id: str) -> List[Dict[str, Any]]:
        """列出平行宇宙分支（有多个子节点的Checkpoint）"""
        all_checkpoints = await self._store.list_story_checkpoints(story_id, limit=200)
        branches = []

        for cp in all_checkpoints:
            children = await self._store.get_children(cp.checkpoint_id)
            if len(children) > 1:
                branches.append({
                    "branch_point": cp.checkpoint_id.value,
                    "reason": cp.trigger_reason,
                    "children": [
                        {"id": c.checkpoint_id.value, "reason": c.trigger_reason}
                        for c in children
                    ],
                })

        return branches

    async def _enforce_retention(self, story_id: str, trigger_type: CheckpointType) -> int:
        """执行保留策略

        Returns:
            删除的Checkpoint数量
        """
        policy = RETENTION_POLICY.get(trigger_type, {})
        max_count = policy.get("max_count")

        if max_count is None:
            return 0  # 永久保留

        checkpoints = await self._store.list_story_checkpoints(
            story_id, trigger_type=trigger_type, limit=1000
        )

        # 超过保留数量的软删除
        deleted = 0
        if len(checkpoints) > max_count:
            to_delete = checkpoints[max_count:]  # 最旧的超出部分
            for cp in to_delete:
                await self._store.soft_delete(cp.checkpoint_id)
                deleted += 1

        if deleted > 0:
            logger.info(f"保留策略执行: 删除了 {deleted} 个 {trigger_type.value} Checkpoint")

        return deleted
