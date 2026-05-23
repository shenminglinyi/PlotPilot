from __future__ import annotations

from typing import List, Optional

from domain.evolution.models import EvolutionState


class ContextPresenter:
    """Hydrates strict EvolutionState into concise T0/T1 prose."""

    def present(self, state: Optional[EvolutionState], max_lines: int = 28) -> str:
        if state is None:
            return ""

        lines: List[str] = ["【叙事状态锁】以下为跨章连续性硬约束，优先级高于普通召回。"]
        scene = state.scene or {}
        if scene.get("time_anchor") or scene.get("location"):
            lines.append(
                f"- 当前时空：{scene.get('time_anchor') or '未标定'}；主要场景：{scene.get('location') or '未标定'}。"
            )
        for action in scene.get("unresolved_actions") or []:
            lines.append(f"- 动作承接：本章开篇必须处理「{str(action)[:120]}」。")
        if scene.get("emotional_residue"):
            lines.append(f"- 情绪余波：{str(scene['emotional_residue'])[:160]}")

        for char_id, char in list((state.characters or {}).items())[:12]:
            status = char.get("status") or "alive"
            loc = char.get("location") or "未知地点"
            if status == "dead":
                lines.append(f"- 硬法则：角色 {char_id} 已死亡，严禁以活人身份行动或说话。")
            elif status in {"missing", "ambiguous"}:
                lines.append(f"- 悬置状态：角色 {char_id} 当前为 {status}，保留不确定性，避免提前坐实。")
            else:
                lines.append(f"- 角色状态：{char_id} 位于 {loc}，状态 {status}。")
            inv = char.get("inventory") or []
            if inv:
                lines.append(f"- 持有物：{char_id} 持有 {', '.join(map(str, inv[:6]))}。")

        for item_id, item in list((state.items or {}).items())[:8]:
            owner = item.get("owner_id")
            loc = item.get("location") or "未知地点"
            lines.append(f"- 关键物品：{item_id} 归属 {owner or '无主'}，位置 {loc}，状态 {item.get('status') or 'unknown'}。")

        facts = state.facts or {}
        for fact in (facts.get("reader_known") or [])[:8]:
            lines.append(f"- 读者已知事实：{fact}")
        for char_id, known in list((facts.get("character_known") or {}).items())[:8]:
            if known:
                lines.append(f"- POV 边界：{char_id} 已知 {', '.join(map(str, known[:5]))}；未列出的隐藏事实不得直接泄露。")

        for debt_id, debt in list((state.debts or {}).items())[:8]:
            status = debt.get("status", "open")
            progress = debt.get("progress") or []
            lines.append(f"- 叙事债务：{debt_id} 状态 {status}，最近推进：{'; '.join(map(str, progress[-2:])) or '暂无'}。")

        for event_id in (state.completed_events or [])[-8:]:
            lines.append(f"- 禁止重复事件：{event_id} 已完成，除非明确回忆，不要当作新事件重写。")

        return "\n".join(lines[:max_lines])
