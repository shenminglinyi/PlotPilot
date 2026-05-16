"""Macro Refactor DTOs"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from domain.novel.value_objects.character_state import BreakpointType


@dataclass
class LogicBreakpoint:
    """逻辑断点 - 人设冲突点

    ★ V2 升级：区分 OOC vs Character Breakout
    - OOC: 真正的人设崩塌（无合理原因的偏离）→ 注入 context_patch 拉回
    - BREAKOUT: 人物突破/高光时刻（有触发原因的偏离）→ 保持张力，不拉回
    - SCAR_TRIGGERED: 伤疤触发后的应激反应 → 延续情绪，不阻断
    """
    event_id: str
    chapter: int
    reason: str  # 冲突原因描述
    tags: List[str]  # 匹配的冲突标签

    # ★ V2: 断点类型（区分 OOC 和 Character Breakout）
    breakpoint_type: BreakpointType = BreakpointType.OOC

    # ★ V2: 关联的伤疤 ID（如果是 SCAR_TRIGGERED 类型）
    related_scar_id: Optional[str] = None

    # ★ V2: 突破原因（如果是 BREAKOUT 类型）
    breakout_reason: Optional[str] = None

    # ★ V2: 涉及的角色 ID
    character_id: Optional[str] = None

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "event_id": self.event_id,
            "chapter": self.chapter,
            "reason": self.reason,
            "tags": self.tags,
            "breakpoint_type": self.breakpoint_type.value,
            "related_scar_id": self.related_scar_id,
            "breakout_reason": self.breakout_reason,
            "character_id": self.character_id,
        }


@dataclass
class BreakpointScanRequest:
    """断点扫描请求"""
    trait: str  # 目标人设标签，如 "冷酷"
    conflict_tags: Optional[List[str]] = None  # 冲突标签列表，如 ["动机:冲动"]


@dataclass
class RefactorProposalRequest:
    """重构提案请求"""
    event_id: str
    author_intent: str  # 作者意图描述
    current_event_summary: str  # 当前事件摘要
    current_tags: List[str]  # 当前标签


@dataclass
class RefactorProposal:
    """重构提案"""
    natural_language_suggestion: str  # 自然语言建议
    suggested_mutations: List[Dict[str, Any]]  # 建议的 mutations
    suggested_tags: List[str]  # 建议的新标签
    reasoning: str  # 推理过程


@dataclass
class ApplyMutationRequest:
    """应用 Mutation 请求"""
    event_id: str
    mutations: List[Dict[str, Any]]  # mutation 列表
    reason: Optional[str] = None  # 修改原因


@dataclass
class ApplyMutationResponse:
    """应用 Mutation 响应"""
    success: bool
    updated_event: Dict[str, Any]  # 更新后的事件
    applied_mutations: List[Dict[str, Any]]  # 已应用的 mutations
