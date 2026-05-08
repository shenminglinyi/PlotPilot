"""规则解析器 — 将 Anti-AI 规则注入到 Prompt 中。

核心功能：
- 从 positive_framing_rules.py 读取正向行为映射
- 从 allowlist_manager.py 读取场景化白名单
- 从 character_state_vector.py 读取角色状态锁
- 将所有规则组装成协议化文本注入到 Prompt
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from application.engine.rules.positive_framing_rules import POSITIVE_FRAMING_MAP
from application.engine.rules.allowlist_manager import get_allowlist_manager
from application.engine.rules.character_state_vector import get_character_state_vector_manager

logger = logging.getLogger(__name__)


class RuleParser:
    """Anti-AI 规则解析器 — 将所有规则组装成 Prompt 可用的文本。"""

    def __init__(self):
        self._allowlist_mgr = get_allowlist_manager()
        self._state_vector_mgr = get_character_state_vector_manager()

    def build_behavior_protocol_block(
        self,
        nervous_habits: str = "",
        scene_type: str = "default",
    ) -> str:
        """构建行为协议文本块（Layer 1+2+3 注入）。

        Args:
            nervous_habits: 角色紧张习惯映射文本
            scene_type: 当前场景类型

        Returns:
            注入到 system prompt 中的行为协议文本。
        """
        # Layer 1+2: 核心协议 + 替换策略
        protocol_lines = [
            "━━━ 核心协议（P1-P5 · 不可违反）━━━",
            "",
            "P1. 信息密度法则",
            "  每个段落必须推进以下至少一项：剧情事实、角色关系、悬念线索、信息差变化。",
            "  写完一段后自查：这段删掉会影响读者理解吗？不会就删掉。",
            "",
            "P2. 感官优先法则",
            "  当你需要表达情绪或氛围时，执行顺序：",
            "  感官细节（温度/光线/声音/触感/气味）→ 动作变化 → 对话内容",
            "  禁止跳过前两步直接写情绪标签。",
            "",
            "P3. 角色差异化法则",
            "  不同角色面对同一事件的反应方式必须不同。",
            "  反应方式 = 角色背景 × 当前身体状态 × 与事件的利益关系。",
        ]

        if nervous_habits:
            protocol_lines.append(f"  每个角色有专属紧张习惯：{nervous_habits}")

        protocol_lines.extend([
            "",
            "P4. 节奏法则",
            "  节奏快 → 句子短，动词前移，主语可省。",
            "  节奏慢 → 长短交替，感官细节穿插。",
            "  禁止连续3句以上长度相近的句子。",
            "",
            "P5. 衔接法则",
            "  节拍间无断点。情绪有惯性。",
            "  上一段在愤怒，这一段不能突然平静。",
            "  禁止用时间词（后来/之后/转眼间）开头省略过渡。",
            "",
            "━━━ 替换策略（检测到B类模式时执行）━━━",
            "",
        ])

        # 从 positive_framing_rules 生成替换策略
        for idx, (rule_key, mapping) in enumerate(POSITIVE_FRAMING_MAP.items(), 1):
            condition = mapping.get("condition", "")
            action = mapping.get("action", "")
            if condition and action:
                protocol_lines.append(
                    f"R{idx}. 场景：{condition}"
                )
                protocol_lines.append(
                    f"    动作：{action}"
                )
                # 注入一个示例（节省 Token）
                examples = mapping.get("examples", [])
                if len(examples) >= 2:
                    protocol_lines.append(f"    {examples[0]}")
                    protocol_lines.append(f"    {examples[1]}")
                protocol_lines.append("")

        # Layer 3: 白名单
        if scene_type != "default":
            protocol_lines.append("")
            protocol_lines.append(self._allowlist_mgr.generate_allowlist_block(scene_type))

        return "\n".join(protocol_lines)

    def build_character_state_lock_block(
        self,
        character_names: List[str],
    ) -> str:
        """构建角色状态锁文本块（Layer 4 注入）。"""
        return self._state_vector_mgr.generate_lock_block(character_names)

    def build_nervous_habits_text(
        self,
        character_names: List[str],
    ) -> str:
        """构建角色紧张习惯映射文本。"""
        return self._state_vector_mgr.get_nervous_habits_text(character_names)

    def build_full_anti_ai_block(
        self,
        character_names: List[str],
        scene_type: str = "default",
    ) -> Dict[str, str]:
        """构建完整的 Anti-AI 注入块。

        Returns:
            {
                "behavior_protocol": 行为协议文本,
                "character_state_lock": 角色状态锁文本,
                "nervous_habits": 紧张习惯映射,
                "allowlist_block": 白名单文本,
            }
        """
        nervous_habits = self.build_nervous_habits_text(character_names)

        return {
            "behavior_protocol": self.build_behavior_protocol_block(
                nervous_habits=nervous_habits,
                scene_type=scene_type,
            ),
            "character_state_lock": self.build_character_state_lock_block(character_names),
            "nervous_habits": nervous_habits,
            "allowlist_block": self._allowlist_mgr.generate_allowlist_block(scene_type),
        }


# 全局单例
_parser: Optional[RuleParser] = None


def get_rule_parser() -> RuleParser:
    """获取全局规则解析器。"""
    global _parser
    if _parser is None:
        _parser = RuleParser()
    return _parser
