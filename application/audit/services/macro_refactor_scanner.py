"""Macro Refactor Scanner Service - V2 升级版

★ V2 核心改变：区分 OOC vs Character Breakout

原逻辑：冲突标签 ∩ 人设 ≠ ∅ → 报 OOC 错误 → context_patch 强行拉回
新逻辑：
  1. 检查角色是否有相关 Scar（伤疤被触发 → SCAR_TRIGGERED）
  2. 检查角色是否有高优先级执念（执念驱动 → BREAKOUT）
  3. 无合理原因 → 真正的 OOC

这解决了"人物弧光冻结"问题：
  当"冷酷"人设因为"挚友之死"而变得"冲动"，
  系统不再强行拉回"理性"，而是判定为 Character Breakout（高光时刻），
  并在 context_patch 中注入"保持张力"而非"强化人设"。
"""
import logging
from typing import List, Optional, Dict, Set
from domain.novel.repositories.narrative_event_repository import NarrativeEventRepository
from domain.novel.repositories.character_state_repository import CharacterStateRepository
from domain.novel.value_objects.character_state import BreakpointType
from application.audit.dtos.macro_refactor_dto import LogicBreakpoint

logger = logging.getLogger(__name__)


class MacroRefactorScanner:
    """宏观重构扫描器 - V2 升级版：Scar 感知 + Breakout 判定"""

    # 内置人设冲突规则映射
    TRAIT_CONFLICT_RULES: Dict[str, List[str]] = {
        "冷酷": ["动机:冲动", "情绪:愤怒", "行为:鲁莽", "情绪:激动"],
        "理性": ["动机:感性", "情绪:激动", "行为:冲动"],
        "谨慎": ["行为:鲁莽", "动机:冲动", "行为:冲动"],
        "温和": ["情绪:愤怒", "行为:暴力", "情绪:激动"],
    }

    def __init__(
        self,
        event_repository: NarrativeEventRepository,
        character_state_repository: Optional[CharacterStateRepository] = None,
    ):
        """初始化扫描器

        Args:
            event_repository: 叙事事件仓储
            character_state_repository: 人物状态仓储（V2 新增，用于 Scar 感知判定）
        """
        self.event_repository = event_repository
        self.character_state_repo = character_state_repository

    def scan_breakpoints(
        self,
        novel_id: str,
        trait: str,
        conflict_tags: Optional[List[str]] = None,
    ) -> List[LogicBreakpoint]:
        """扫描人设冲突断点（V1 兼容接口）

        Args:
            novel_id: 小说 ID
            trait: 目标人设标签（如 "冷酷"）
            conflict_tags: 自定义冲突标签列表（如果提供，覆盖内置规则）

        Returns:
            冲突断点列表
        """
        # 确定冲突标签
        if conflict_tags is not None:
            target_conflict_tags = set(conflict_tags)
        else:
            target_conflict_tags = set(self.TRAIT_CONFLICT_RULES.get(trait, []))

        if not target_conflict_tags:
            logger.warning(f"No conflict rules defined for trait '{trait}' and no custom tags provided")
            return []

        # 获取所有事件
        events = self.event_repository.list_up_to_chapter(novel_id, 999999)

        # 扫描冲突
        breakpoints = []
        for event in events:
            event_tags = set(event.get("tags", []))
            conflicting_tags = event_tags & target_conflict_tags

            if conflicting_tags:
                # ★ V2: 尝试判定 Breakout 类型
                breakpoint_type, scar_id, breakout_reason, character_id = (
                    self._classify_breakpoint(novel_id, trait, list(conflicting_tags), event)
                )

                reason = self._generate_conflict_reason_v2(
                    trait, list(conflicting_tags), breakpoint_type, breakout_reason
                )

                breakpoint = LogicBreakpoint(
                    event_id=event["event_id"],
                    chapter=event["chapter_number"],
                    reason=reason,
                    tags=list(conflicting_tags),
                    breakpoint_type=breakpoint_type,
                    related_scar_id=scar_id,
                    breakout_reason=breakout_reason,
                    character_id=character_id,
                )
                breakpoints.append(breakpoint)

        # 统计各类型数量
        ooc_count = sum(1 for bp in breakpoints if bp.breakpoint_type == BreakpointType.OOC)
        breakout_count = sum(1 for bp in breakpoints if bp.breakpoint_type == BreakpointType.CHARACTER_BREAKOUT)
        scar_count = sum(1 for bp in breakpoints if bp.breakpoint_type == BreakpointType.SCAR_TRIGGERED)

        logger.info(
            f"Scanned {len(events)} events for trait '{trait}': "
            f"OOC={ooc_count}, Breakout={breakout_count}, Scar={scar_count}"
        )
        return breakpoints

    def _classify_breakpoint(
        self,
        novel_id: str,
        trait: str,
        conflicting_tags: List[str],
        event: dict,
    ) -> tuple:
        """判定人设偏离的类型：OOC / Breakout / Scar Triggered

        Returns:
            (breakpoint_type, related_scar_id, breakout_reason, character_id)
        """
        if not self.character_state_repo:
            # 无人物状态仓储时，降级为纯 OOC 判定（V1 兼容）
            return (BreakpointType.OOC, None, None, None)

        # 尝试从事件中提取涉及的角色
        character_id = self._extract_character_from_event(event)
        if not character_id:
            return (BreakpointType.OOC, None, None, None)

        # 获取角色状态
        char_state = self.character_state_repo.get(character_id, novel_id)
        if not char_state:
            return (BreakpointType.OOC, None, None, character_id)

        # 1. 检查伤疤触发
        triggered_scars = char_state.check_scar_trigger(conflicting_tags)
        if triggered_scars:
            scar = triggered_scars[0]  # 取最强的伤疤
            return (
                BreakpointType.SCAR_TRIGGERED,
                scar.id,
                f"角色伤疤'{scar.impact}'被触发（来源：第{scar.source_chapter}章 {scar.source_event}）",
                character_id,
            )

        # 2. 检查高优先级执念
        high_priority_motivations = [
            m for m in char_state.get_active_motivations() if m.priority >= 8
        ]
        if high_priority_motivations:
            top_motivation = high_priority_motivations[0]
            return (
                BreakpointType.CHARACTER_BREAKOUT,
                None,
                f"角色执念'{top_motivation.description}'驱动的行为突破（来源：第{top_motivation.source_chapter}章 {top_motivation.source_event}）",
                character_id,
            )

        # 3. 无合理原因的偏离
        return (BreakpointType.OOC, None, None, character_id)

    def _extract_character_from_event(self, event: dict) -> Optional[str]:
        """从叙事事件中提取涉及的角色 ID

        尝试多种方式：
        1. mutations 中的 entity_id
        2. event_summary 中的角色名（需要 Bible 匹配）
        """
        # 方式 1: mutations 中的 entity_id
        mutations = event.get("mutations", [])
        if mutations and isinstance(mutations, list):
            for m in mutations:
                if isinstance(m, dict) and m.get("entity_id"):
                    return m["entity_id"]

        # 方式 2: 暂时无法从 event_summary 中提取角色名
        # 这需要 Bible 服务的配合，后续可以增强
        return None

    def _generate_conflict_reason_v2(
        self,
        trait: str,
        conflicting_tags: List[str],
        breakpoint_type: BreakpointType,
        breakout_reason: Optional[str],
    ) -> str:
        """生成 V2 版本的冲突原因描述"""
        tags_str = "、".join(conflicting_tags)

        if breakpoint_type == BreakpointType.OOC:
            return f"人设 '{trait}' 与事件标签 [{tags_str}] 冲突（无合理原因的偏离）"
        elif breakpoint_type == BreakpointType.CHARACTER_BREAKOUT:
            return f"人设 '{trait}' 与事件标签 [{tags_str}] 冲突，但这是人物突破时刻：{breakout_reason}"
        elif breakpoint_type == BreakpointType.SCAR_TRIGGERED:
            return f"人设 '{trait}' 与事件标签 [{tags_str}] 冲突，但这是伤疤触发的应激反应：{breakout_reason}"
        else:
            return f"人设 '{trait}' 与事件标签 [{tags_str}] 冲突"
