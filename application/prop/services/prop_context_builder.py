"""PropContextBuilder — 生成写章用的道具上下文文本块。

输出三种块：
1. prop_fact_lock: T0 级别，道具当前状态（不可违反的事实）
2. prop_suggestions: 建议引入的道具（可忽略）
3. prop_warnings: 一致性警告（红色提示）
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

from domain.prop.entities.prop import Prop
from domain.prop.repositories.prop_repository import PropRepository
from domain.prop.repositories.prop_event_repository import PropEventRepository
from domain.prop.value_objects.lifecycle_state import LifecycleState

logger = logging.getLogger(__name__)


class PropContextBuilder:
    """从道具仓储构建写章上下文文本，注入 DAG 节点。"""

    def __init__(
        self,
        prop_repo: PropRepository,
        event_repo: PropEventRepository,
    ) -> None:
        self._prop_repo = prop_repo
        self._event_repo = event_repo

    def build_for_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        involved_character_ids: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """返回 {"prop_fact_lock": ..., "prop_suggestions": ..., "prop_warnings": ...}。"""
        all_props = self._prop_repo.list_by_novel(novel_id)
        active = [p for p in all_props if p.is_active_in_chapter(chapter_number)]

        if involved_character_ids:
            char_set = set(involved_character_ids)
            relevant = [
                p for p in active
                if p.holder_character_id in char_set or p.holder_character_id is None
            ]
        else:
            relevant = active

        fact_lock = self._build_fact_lock(relevant)
        suggestions = self._build_suggestions(all_props, chapter_number)
        warnings = self._build_warnings(relevant)

        return {
            "prop_fact_lock": fact_lock,
            "prop_suggestions": suggestions,
            "prop_warnings": warnings,
        }

    def _build_fact_lock(self, props: List[Prop]) -> str:
        if not props:
            return ""
        lines = ["[道具状态锁 — 不可违反]"]
        for p in props:
            holder_note = f"持有者: {p.holder_character_id}" if p.holder_character_id else "无持有者"
            state_note = p.display_state()
            lines.append(f"- {p.name}（{holder_note}）: {state_note}")
            if p.lifecycle_state == LifecycleState.DAMAGED:
                lines.append(f"  ⚠ 已损毁，需描述损毁后的表现")
        return "\n".join(lines)

    def _build_suggestions(self, all_props: List[Prop], chapter: int) -> str:
        dormant_long = [
            p for p in all_props
            if p.lifecycle_state in (LifecycleState.DORMANT, LifecycleState.INTRODUCED)
            and (p.introduced_chapter is None or chapter - (p.introduced_chapter or 0) > 3)
        ]
        if not dormant_long:
            return ""
        lines = ["[道具建议引入 — 可忽略]"]
        for p in dormant_long[:5]:
            holder_note = f"由{p.holder_character_id}持有" if p.holder_character_id else "无持有者"
            lines.append(f"- {p.name}（{p.display_state()}，{holder_note}）: {p.description[:60]}")
        return "\n".join(lines)

    def _build_warnings(self, props: List[Prop]) -> str:
        warnings: List[str] = []
        for p in props:
            if p.lifecycle_state == LifecycleState.DAMAGED:
                warnings.append(
                    f"⚠ {p.name} 已损毁（第{p.introduced_chapter}章前），请勿描述为完整状态"
                )
        if not warnings:
            return ""
        return "[一致性警告]\n" + "\n".join(warnings)
