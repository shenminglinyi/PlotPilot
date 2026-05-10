"""视角守门人 — 视角选择与伏笔绑定层级验证

两大检测维度：
1. 视角选择器：信息差/弱势方/核心当事人
2. 伏笔绑定层级验证：character<faction<event<world

视角选择原则：
- 谁最不知道真相？→ 用TA的视角，制造信息差
- 谁最弱？→ 用TA的视角，读者代入感最强
- 谁是核心当事人？→ 用TA的视角，最直接

伏笔绑定层级：
- character(1)：❌ 不推荐（格局小）
- faction(2)：⚠️ 可接受
- event(3)：✅ 推荐
- world(4)：🌟 最佳
- 核心伏笔(>0.8)必须绑定event或world
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ViewpointViolation:
    """视角违规"""
    violation_type: str    # suboptimal_viewpoint / weak_binding / viewpoint_leak
    severity: float
    description: str
    suggestion: str

    @property
    def type_name(self) -> str:
        names = {
            "suboptimal_viewpoint": "非最佳视角",
            "weak_binding": "伏笔绑定层级不足",
            "viewpoint_leak": "视角泄露",
        }
        return names.get(self.violation_type, self.violation_type)


class ViewpointGuardrail:
    """视角守门人"""

    # 伏笔绑定层级
    BINDING_LEVELS = {
        "character": 1,
        "faction": 2,
        "event": 3,
        "world": 4,
    }

    # 视角泄露检测模式（知道不该知道的信息）
    # 限制性第三人称中不应出现其他角色的内心描写
    _VIEWPOINT_LEAK_PATTERNS = [
        r'(?:(?:而对面的|对面的|旁边的|另一边的|另一方的|对面的|旁边的|身后的).{0,6}(?:心里|心中|心想|暗想|暗自|想到|思忖|盘算|思量|内心|心下))',
        r'(?:他知道.{0,4}(?:其实|实际上|真相))',
        r'(?:她/他.{0,4}(?:心里想|心想|暗想|暗自想|思忖|盘算))',
    ]

    # 其他角色内心活动的关键词
    _OTHER_MIND_KEYWORDS = [
        "心里想", "心想", "暗想", "暗自", "思忖", "盘算", "思量",
        "心中", "心下", "内心", "心底",
    ]

    def check(
        self,
        text: str,
        scene_info: Dict[str, Any],
        foreshadows: List[Dict[str, Any]] = None,
    ) -> Tuple[float, List[ViewpointViolation]]:
        """检查视角和伏笔绑定

        Args:
            text: 待检查文本
            scene_info: 场景信息 {
                viewpoint_character: str,
                characters_present: List[str],
                key_event: str,
                information_asymmetry: Dict[str, Any],
            }
            foreshadows: 活跃伏笔列表

        Returns:
            (score, violations)
        """
        violations: List[ViewpointViolation] = []

        # 1. 视角选择器
        violations.extend(self._check_viewpoint_selection(text, scene_info))

        # 2. 视角泄露检测
        violations.extend(self._check_viewpoint_leak(text, scene_info))

        # 3. 伏笔绑定层级验证
        if foreshadows:
            violations.extend(self._check_foreshadow_binding(foreshadows))

        if not violations:
            return 1.0, []

        total_penalty = sum(v.severity for v in violations)
        score = max(0.0, 1.0 - total_penalty * 0.15)

        return score, violations

    def _check_viewpoint_selection(
        self,
        text: str,
        scene_info: Dict[str, Any],
    ) -> List[ViewpointViolation]:
        """视角选择器 — 检查是否选择了最佳视角"""
        violations = []

        viewpoint = scene_info.get("viewpoint_character", "")
        characters = scene_info.get("characters_present", [])
        key_event = scene_info.get("key_event", "")
        asymmetry = scene_info.get("information_asymmetry", {})

        if not viewpoint or not characters:
            return violations

        # 原则1：谁最不知道真相？
        if asymmetry:
            least_informed = min(
                characters,
                key=lambda c: len(asymmetry.get(c, {}).get("known_facts", [])),
            )
            if least_informed != viewpoint:
                violations.append(ViewpointViolation(
                    violation_type="suboptimal_viewpoint",
                    severity=0.4,
                    description=f"当前视角为{viewpoint}，但{least_informed}掌握最少信息，用TA的视角信息差更大",
                    suggestion=f"考虑切换到{least_informed}的视角，制造更多悬念",
                ))

        # 原则2：谁最弱？（在冲突场景中）
        if key_event and "战斗" in key_event or "冲突" in key_event:
            weak_markers = ["受伤", "后退", "劣势", "不敌", "苦战"]
            if any(marker in text for marker in weak_markers):
                pass  # 需要更多上下文判断

        return violations

    def _check_viewpoint_leak(
        self,
        text: str,
        scene_info: Dict[str, Any],
    ) -> List[ViewpointViolation]:
        """视角泄露检测 — 限制性视角中不应知道他人内心"""
        violations = []

        viewpoint = scene_info.get("viewpoint_character", "")
        characters = scene_info.get("characters_present", [])

        if not viewpoint or not characters or len(characters) < 2:
            return violations

        # 查找文本中其他角色的内心描写
        other_chars = [c for c in characters if c != viewpoint]

        for other in other_chars:
            # 检查是否有 "XX心里想"、"XX心想"、"XX暗想" 等内心描写
            for keyword in self._OTHER_MIND_KEYWORDS:
                pattern = rf'{other}.{{0,4}}{keyword}'
                if re.search(pattern, text):
                    violations.append(ViewpointViolation(
                        violation_type="viewpoint_leak",
                        severity=0.8,
                        description=f"视角泄露：以{viewpoint}的限制性视角，不应知道{other}的内心活动",
                        suggestion=f"改为通过{other}的外在表现来暗示其想法，而非直接描写内心",
                    ))
                    break  # 每个角色只报一次

        return violations

    def _check_foreshadow_binding(
        self,
        foreshadows: List[Dict[str, Any]],
    ) -> List[ViewpointViolation]:
        """伏笔绑定层级验证"""
        violations = []

        for f in foreshadows:
            emotional_weight = f.get("emotional_weight", 0.5)
            binding_level = f.get("binding_level", 1)
            description = f.get("description", "未知伏笔")

            # 核心伏笔必须绑定event或world
            if emotional_weight > 0.8 and binding_level < 3:
                binding_name = {1: "角色", 2: "势力", 3: "事件", 4: "世界"}.get(binding_level, "未知")
                violations.append(ViewpointViolation(
                    violation_type="weak_binding",
                    severity=0.7,
                    description=f"核心伏笔'{description}'(权重{emotional_weight})仅绑定到{binding_name}层级，格局不够大",
                    suggestion="核心伏笔应绑定到'事件'或'世界'层级，提升叙事格局",
                ))

        return violations

    def recommend_viewpoint(
        self,
        characters: List[Dict[str, Any]],
        key_event: str = "",
    ) -> Dict[str, Any]:
        """推荐最佳视角角色

        Args:
            characters: 角色列表 [{name, knowledge_level, power_level, involvement}]
            key_event: 关键事件

        Returns:
            推荐结果 {recommended, reasoning, alternatives}
        """
        if not characters:
            return {"recommended": None, "reasoning": "无角色信息", "alternatives": []}

        # 评分
        scored = []
        for char in characters:
            score = 0
            reasons = []

            # 信息差越大越好（知识水平越低，信息差越大）
            knowledge = char.get("knowledge_level", 0.5)
            score += (1 - knowledge) * 3
            if knowledge < 0.3:
                reasons.append(f"{char['name']}对真相最不知情，信息差最大")

            # 力量越弱越容易代入
            power = char.get("power_level", 0.5)
            score += (1 - power) * 2
            if power < 0.3:
                reasons.append(f"{char['name']}处于弱势，读者代入感更强")

            # 核心当事人权重
            involvement = char.get("involvement", 0.5)
            score += involvement * 2
            if involvement > 0.7:
                reasons.append(f"{char['name']}是核心当事人")

            scored.append({
                "name": char["name"],
                "score": score,
                "reasons": reasons,
            })

        # 排序
        scored.sort(key=lambda x: x["score"], reverse=True)

        return {
            "recommended": scored[0]["name"] if scored else None,
            "reasoning": scored[0]["reasons"] if scored else [],
            "alternatives": [s["name"] for s in scored[1:3]],
        }
