"""CharacterMask值对象 — 折叠地质叠层后的当前面具快照

核心用途：
- 在T0层注入，控制角色行为的四维一致性
- validate_behavior()：验证行为是否符合角色设定
- 由Character.compute_mask()计算生成

注入格式示例：
[角色状态锁定 - 林羽（第50章当前阶段）]
当前核心信念：只有力量能保护自己，轻信必死。
当前语言指纹：短句为主，陈述语气，透着背叛后的阴沉。
身上带着的旧伤：左肩曾被恩师刺伤，极其排斥别人站在他左后方。
绝对禁忌：绝不杀手无寸铁之人。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass(frozen=True)
class CharacterMask:
    """角色当前面具 — 折叠地质叠层后的快照

    在T0层注入，控制角色行为的四维一致性：
    1. core_belief：决定价值选择
    2. moral_taboos：决定底线
    3. voice_profile：决定台词风格
    4. active_wounds：决定条件反射
    """
    character_id: str
    name: str
    core_belief: str
    moral_taboos: List[str] = field(default_factory=list)
    voice_style: str = "default"
    sentence_pattern: str = "mixed"
    metaphors: List[str] = field(default_factory=list)
    active_wounds: List[Dict[str, str]] = field(default_factory=list)
    chapter_number: int = 0

    def validate_behavior(self, action: str, context: str = "") -> Dict[str, Any]:
        """验证行为是否符合角色设定

        检查项：
        - 是否触碰禁忌？
        - 是否符合信念？
        - 是否触发创伤反应？

        Args:
            action: 角色行为描述
            context: 场景上下文

        Returns:
            {"valid": bool, "warnings": List[str], "suggestions": List[str]}
        """
        warnings = []
        suggestions = []

        # 1. 检查是否触碰禁忌
        for taboo in self.moral_taboos:
            if taboo in action:
                warnings.append(f"行为触碰绝对禁忌：{taboo}")
                suggestions.append(f"需要为触碰禁忌提供充分动机和代价")

        # 2. 检查创伤触发
        for wound in self.active_wounds:
            trigger = wound.get("trigger", "")
            if trigger and trigger in context:
                warnings.append(f"触发旧伤反应：{wound.get('description', '')}")
                suggestions.append(f"应描写条件反射：{wound.get('effect', '')}")

        # 3. 检查语言风格一致性（粗略）
        if self.voice_style == "惜字如金" and len(action) > 200:
            warnings.append("角色语言风格为惜字如金，但行为描述过长")
        elif self.voice_style == "话多" and len(action) < 20:
            warnings.append("角色语言风格为话多，但行为描述过短")

        # 4. 核心信念冲突检测
        if self.core_belief:
            belief = self.core_belief
            # 不信任类信念 → 检测轻易信任行为
            distrust_keywords = ["不信任", "警惕", "谨慎", "轻信", "防备", "不信",
                                 "软肋", "致命", "危险", "不可信"]
            if any(kw in belief for kw in distrust_keywords):
                import re
                trust_patterns = [
                    rf'{self.name}.{{0,8}}(毫不犹豫地相信|完全信任|放心地|毫无戒备|毫无防备|轻信)',
                    rf'{self.name}.{{0,4}}(相信|信任|放心).{{0,6}}(陌生|别人|他人)',
                ]
                for pattern in trust_patterns:
                    if re.search(pattern, action):
                        warnings.append(f"行为与核心信念冲突：{belief}，但出现了轻易信任的描写")
                        suggestions.append("添加内心挣扎或表面配合暗中设防的描写")
                        break

            # 力量/暴力类信念 → 检测软弱行为
            power_keywords = ["力量", "强者为尊", "弱肉强食"]
            if any(kw in belief for kw in power_keywords):
                import re
                weak_patterns = [rf'{self.name}.{{0,8}}(退缩|害怕|求饶|示弱|妥协)']
                for pattern in weak_patterns:
                    if re.search(pattern, action):
                        warnings.append(f"行为与核心信念冲突：{belief}，但出现了软弱行为")
                        suggestions.append("如确有软弱，需要提供充分的外部压力描写")
                        break

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
            "suggestions": suggestions,
        }

    def to_t0_fact_lock(self) -> str:
        """生成T0层Fact Lock注入格式"""
        lines = [f"[角色状态锁定 - {self.name}（第{self.chapter_number}章当前阶段）]"]
        lines.append(f"当前核心信念：{self.core_belief}")

        voice_parts = []
        if self.voice_style != "default":
            voice_parts.append(f"风格：{self.voice_style}")
        if self.sentence_pattern != "mixed":
            voice_parts.append(f"句式：{self.sentence_pattern}")
        if self.metaphors:
            voice_parts.append(f"隐喻：{'、'.join(self.metaphors[:3])}")
        if voice_parts:
            lines.append(f"当前语言指纹：{'；'.join(voice_parts)}")

        for wound in self.active_wounds:
            desc = wound.get("description", "")
            trigger = wound.get("trigger", "")
            effect = wound.get("effect", "")
            if desc:
                lines.append(f"身上带着的旧伤：{desc}（触发：{trigger} → {effect}）")

        if self.moral_taboos:
            lines.append(f"绝对禁忌：{'、'.join(self.moral_taboos)}")

        return "\n".join(lines)

    @classmethod
    def from_character_dict(cls, data: Dict[str, Any], chapter_number: int = 0) -> CharacterMask:
        """从Character.compute_mask()的输出创建CharacterMask"""
        voice_data = data.get("voice_profile", {})
        wounds_data = data.get("active_wounds", [])

        # 处理wounds格式
        normalized_wounds = []
        for w in wounds_data:
            if isinstance(w, dict):
                normalized_wounds.append(w)
            elif isinstance(w, str):
                normalized_wounds.append({"description": w, "trigger": "", "effect": ""})

        return cls(
            character_id=data.get("character_id", ""),
            name=data.get("name", ""),
            core_belief=data.get("core_belief", ""),
            moral_taboos=data.get("moral_taboos", []),
            voice_style=voice_data.get("style", "default"),
            sentence_pattern=voice_data.get("sentence_pattern", "mixed"),
            metaphors=voice_data.get("metaphors", []),
            active_wounds=normalized_wounds,
            chapter_number=chapter_number,
        )
