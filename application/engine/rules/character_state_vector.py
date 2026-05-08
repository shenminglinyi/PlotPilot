"""角色状态向量 — Layer 4: 强制注入角色锚点防止记忆漂移。

核心机制：
- 声线指纹（VoicePrint）：每个角色的语言习惯/口癖/句式偏好
- 紧张习惯（NervousHabit）：角色面对压力的专属肢体反应
- 反应模式（ReactionPattern）：基于角色背景的差异化反应模板
- 信息边界（InfoBoundary）：角色已知/未知的硬边界
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VoicePrint:
    """声线指纹 — 角色的语言DNA。"""
    character_name: str
    sentence_length_preference: str = "medium"  # short/medium/long
    vocabulary_style: str = "colloquial"  # colloquial/literary/formal/slang
    common_expressions: List[str] = field(default_factory=list)  # 口头禅
    punctuation_habits: str = "normal"  # sparse/normal/dense（省略号、破折号偏好）
    tone_markers: List[str] = field(default_factory=list)  # 语气词（啊、嘛、呢、吧）
    description: str = ""


@dataclass
class NervousHabit:
    """紧张习惯 — 角色面对压力时的专属肢体反应。"""
    character_name: str
    primary: str = ""  # 主习惯：如"摸后脑勺"
    secondary: str = ""  # 次习惯：如"抿嘴唇"
    stress_indicator: str = ""  # 极度压力表现：如"指甲掐进掌心"
    relaxation_indicator: str = ""  # 放松表现：如"肩膀明显松弛下来"


@dataclass
class ReactionPattern:
    """反应模式 — 基于角色背景的差异化反应。"""
    character_name: str
    fight_response: str = "confront"  # confront/evade/freeze/manipulate
    emotional_expression: str = "action"  # action/words/suppress/explosive
    decision_speed: str = "impulsive"  # impulsive/calculated/deferred
    trust_tendency: str = "cautious"  # naive/cautious/trusting/hostile
    description: str = ""


@dataclass
class InfoBoundary:
    """信息边界 — 角色已知/未知的硬边界。"""
    character_name: str
    known_facts: List[str] = field(default_factory=list)
    unknown_facts: List[str] = field(default_factory=list)
    misbeliefs: List[str] = field(default_factory=list)  # 角色错误相信的事


@dataclass
class CharacterStateVector:
    """角色状态向量 — 完整的角色锚点。"""
    character_name: str
    physical_state: str = ""  # 当前身体状态
    emotional_baseline: str = ""  # 情绪底色
    voice_print: Optional[VoicePrint] = None
    nervous_habit: Optional[NervousHabit] = None
    reaction_pattern: Optional[ReactionPattern] = None
    info_boundary: Optional[InfoBoundary] = None
    chapter_context: str = ""  # 本章上下文

    def to_lock_text(self) -> str:
        """生成角色状态锁的文本（注入到 Prompt 中）。"""
        lines = [f"━━━ 角色状态锁：{self.character_name} ━━━"]
        lines.append(f"- 身体：{self.physical_state or '正常'}")
        lines.append(f"- 情绪底色：{self.emotional_baseline or '平稳'}")

        if self.nervous_habit:
            lines.append(f"- 紧张习惯：{self.nervous_habit.primary}")
            if self.nervous_habit.secondary:
                lines.append(f"  次习惯：{self.nervous_habit.secondary}")

        if self.voice_print:
            vp = self.voice_print
            lines.append(f"- 声线指纹：{vp.description or vp.vocabulary_style}")
            if vp.common_expressions:
                lines.append(f"  口头禅：{'、'.join(vp.common_expressions[:3])}")

        if self.reaction_pattern:
            rp = self.reaction_pattern
            lines.append(f"- 反应模式：{rp.description or rp.fight_response}")

        if self.info_boundary:
            ib = self.info_boundary
            if ib.unknown_facts:
                lines.append(f"- 未知信息：{'; '.join(ib.unknown_facts[:3])}")

        lines.append("")
        lines.append("🔒 锁定规则：")
        lines.append(f"1. 声线指纹不可偏离")
        lines.append(f"2. 紧张习惯必须一致——遇到压力时{self.character_name}会{self.nervous_habit.primary if self.nervous_habit else '有特定反应'}")
        lines.append(f"3. 信息边界不可突破——{self.character_name}不知道的事不能写他知道")
        lines.append(f"4. 身体状态有惯性——不会突然恢复或恶化")

        return "\n".join(lines)


class CharacterStateVectorManager:
    """角色状态向量管理器 — 维护所有角色的状态向量。"""

    def __init__(self):
        self._vectors: Dict[str, CharacterStateVector] = {}

    def get_or_create(self, character_name: str) -> CharacterStateVector:
        """获取或创建角色状态向量。"""
        if character_name not in self._vectors:
            self._vectors[character_name] = CharacterStateVector(
                character_name=character_name,
                voice_print=VoicePrint(character_name=character_name),
                nervous_habit=NervousHabit(character_name=character_name),
                reaction_pattern=ReactionPattern(character_name=character_name),
                info_boundary=InfoBoundary(character_name=character_name),
            )
        return self._vectors[character_name]

    def update_from_bible(self, character_name: str, bible_data: Dict[str, Any]) -> None:
        """从 Bible 数据更新角色状态向量。"""
        csv = self.get_or_create(character_name)

        # 更新身体状态
        if "physical_state" in bible_data:
            csv.physical_state = bible_data["physical_state"]

        # 更新情绪底色
        if "emotional_baseline" in bible_data:
            csv.emotional_baseline = bible_data["emotional_baseline"]

        # 更新声线指纹
        if "voice_print" in bible_data:
            vp_data = bible_data["voice_print"]
            if csv.voice_print is None:
                csv.voice_print = VoicePrint(character_name=character_name)
            for k, v in vp_data.items():
                if hasattr(csv.voice_print, k):
                    setattr(csv.voice_print, k, v)

        # 更新紧张习惯
        if "nervous_habit" in bible_data:
            nh_data = bible_data["nervous_habit"]
            if csv.nervous_habit is None:
                csv.nervous_habit = NervousHabit(character_name=character_name)
            for k, v in nh_data.items():
                if hasattr(csv.nervous_habit, k):
                    setattr(csv.nervous_habit, k, v)

        # 更新反应模式
        if "reaction_pattern" in bible_data:
            rp_data = bible_data["reaction_pattern"]
            if csv.reaction_pattern is None:
                csv.reaction_pattern = ReactionPattern(character_name=character_name)
            for k, v in rp_data.items():
                if hasattr(csv.reaction_pattern, k):
                    setattr(csv.reaction_pattern, k, v)

        logger.info("CharacterStateVector: 已更新 %s 的状态向量", character_name)

    def generate_lock_block(self, character_names: List[str]) -> str:
        """为指定角色生成状态锁文本块（注入到 Prompt）。"""
        blocks = []
        for name in character_names:
            csv = self._vectors.get(name)
            if csv:
                blocks.append(csv.to_lock_text())
        return "\n\n".join(blocks)

    def get_nervous_habits_text(self, character_names: List[str]) -> str:
        """生成角色紧张习惯映射文本。"""
        parts = []
        for name in character_names:
            csv = self._vectors.get(name)
            if csv and csv.nervous_habit and csv.nervous_habit.primary:
                parts.append(f"{name}：{csv.nervous_habit.primary}")
        return "；".join(parts) if parts else "由角色背景决定"


# 全局单例
_manager: Optional[CharacterStateVectorManager] = None


def get_character_state_vector_manager() -> CharacterStateVectorManager:
    """获取全局角色状态向量管理器。"""
    global _manager
    if _manager is None:
        _manager = CharacterStateVectorManager()
    return _manager
