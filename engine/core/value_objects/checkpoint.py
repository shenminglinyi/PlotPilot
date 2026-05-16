"""Checkpoint值对象 — Git式版本控制

核心设计：
- 每个Checkpoint是一个完整的不可变快照
- 通过parent_id构建树状结构
- 支持"平行宇宙"（多剧情分支）
- 相当于Git的commit

触发策略（A+C混合方案）：
- 章节完成 → CHAPTER（保留最近10章）
- 幕切换 → ACT（永久保留）
- 大纲变更 → MILESTONE（保留最近5个）
- 用户干预 → MANUAL（保留24小时）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional
import uuid


class CheckpointType(str, Enum):
    """Checkpoint类型"""
    CHAPTER = "chapter"        # 章节完成
    ACT = "act"                # 幕切换
    MILESTONE = "milestone"    # 大纲变更
    MANUAL = "manual"          # 用户干预


# 保留策略
RETENTION_POLICY = {
    CheckpointType.CHAPTER: {"max_count": 10, "permanent": False},
    CheckpointType.ACT: {"max_count": None, "permanent": True},
    CheckpointType.MILESTONE: {"max_count": 5, "permanent": False},
    CheckpointType.MANUAL: {"max_hours": 24, "permanent": False},
}


@dataclass(frozen=True)
class CheckpointId:
    """Checkpoint ID值对象"""
    value: str

    @classmethod
    def generate(cls) -> CheckpointId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Checkpoint:
    """Checkpoint值对象（不可变快照）

    Git式版本控制：
    - 每个Checkpoint是一个完整的快照
    - 通过parent_id构建树状结构
    - 支持"平行宇宙"（多剧情分支）
    - 相当于Git的commit对象

    快照内容（snapshot_payload）：
    - story_state: 故事状态（当前幕、章节数、阶段等）
    - character_masks: 角色当前面具（character_id → CharacterMask）
    - emotion_ledger: 情绪账本
    - active_foreshadows: 活跃伏笔列表
    - outline: 当前大纲
    - recent_chapters_summary: 近期章节摘要
    """
    checkpoint_id: CheckpointId
    story_id: str
    parent_id: Optional[CheckpointId]
    trigger_type: CheckpointType
    trigger_reason: str

    # 快照内容
    story_state: Dict[str, Any] = field(default_factory=dict)
    character_masks: Dict[str, Any] = field(default_factory=dict)
    emotion_ledger: Dict[str, Any] = field(default_factory=dict)
    active_foreshadows: List[str] = field(default_factory=list)
    outline: str = ""
    recent_chapters_summary: str = ""

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @classmethod
    def create(
        cls,
        story_id: str,
        trigger_type: CheckpointType,
        trigger_reason: str,
        story_state: Dict[str, Any],
        character_masks: Dict[str, Any],
        emotion_ledger: Dict[str, Any],
        active_foreshadows: List[str],
        parent_id: Optional[CheckpointId] = None,
        outline: str = "",
        recent_chapters_summary: str = "",
    ) -> Checkpoint:
        """工厂方法：创建Checkpoint"""
        return cls(
            checkpoint_id=CheckpointId.generate(),
            story_id=story_id,
            parent_id=parent_id,
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            story_state=story_state,
            character_masks=character_masks,
            emotion_ledger=emotion_ledger,
            active_foreshadows=active_foreshadows,
            outline=outline,
            recent_chapters_summary=recent_chapters_summary,
        )

    def is_root(self) -> bool:
        """是否为根节点"""
        return self.parent_id is None

    def get_retention_policy(self) -> Dict[str, Any]:
        """获取保留策略"""
        return RETENTION_POLICY.get(self.trigger_type, {"max_count": 5, "permanent": False})

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "checkpoint_id": self.checkpoint_id.value,
            "story_id": self.story_id,
            "parent_id": self.parent_id.value if self.parent_id else None,
            "trigger_type": self.trigger_type.value,
            "trigger_reason": self.trigger_reason,
            "story_state": self.story_state,
            "character_masks": self.character_masks,
            "emotion_ledger": self.emotion_ledger,
            "active_foreshadows": self.active_foreshadows,
            "outline": self.outline,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Checkpoint:
        """从字典反序列化"""
        return cls(
            checkpoint_id=CheckpointId(data["checkpoint_id"]),
            story_id=data["story_id"],
            parent_id=CheckpointId(data["parent_id"]) if data.get("parent_id") else None,
            trigger_type=CheckpointType(data["trigger_type"]),
            trigger_reason=data["trigger_reason"],
            story_state=data.get("story_state", {}),
            character_masks=data.get("character_masks", {}),
            emotion_ledger=data.get("emotion_ledger", {}),
            active_foreshadows=data.get("active_foreshadows", []),
            outline=data.get("outline", ""),
            recent_chapters_summary=data.get("recent_chapters_summary", ""),
            created_at=data.get("created_at", ""),
        )
