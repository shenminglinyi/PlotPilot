"""叙事节奏守门人 — 控制场景的叙事节奏

核心原则：
- 打斗场景：简洁、动词密集、短句为主
- 揭秘对话：节奏放慢、长对话、情绪铺垫
- 大事件：精准描写、不加冗余修饰

ChapterBudgetAllocator集成：
- 不同阶段有不同预算分配
- 开局期：日常30%，发展期：20%，收敛期：10%，终局期：0%
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class RhythmViolation:
    """节奏违规"""
    violation_type: str    # action_bloat / reveal_rush / event_detour
    severity: float
    description: str
    suggestion: str

    @property
    def type_name(self) -> str:
        names = {
            "action_bloat": "打斗场景臃肿",
            "reveal_rush": "揭秘场景仓促",
            "event_detour": "大事件跑偏",
        }
        return names.get(self.violation_type, self.violation_type)


class RhythmGuardrail:
    """叙事节奏守门人"""

    # 打斗场景关键词
    ACTION_KEYWORDS = [
        "出剑", "挥刀", "拳", "踢", "斩", "刺", "挡", "闪", "退",
        "攻击", "防守", "反击", "冲锋", "对决", "搏杀",
    ]

    # 揭秘场景关键词
    REVEAL_KEYWORDS = [
        "真相", "秘密", "原来", "幕后", "隐藏", "真实身份",
        "坦白", "告白", "揭露", "揭露", "坦承",
    ]

    # 大事件关键词
    MAJOR_EVENT_KEYWORDS = [
        "决战", "大战", "攻城", "围剿", "天劫", "渡劫",
        "登基", "继位", "灭门", "屠城",
    ]

    def check(
        self,
        text: str,
        scene_type: str = "auto",
        chapter_budget: Dict[str, Any] = None,
    ) -> Tuple[float, List[RhythmViolation]]:
        """检查叙事节奏

        Args:
            text: 待检查文本
            scene_type: 场景类型 (auto/action/reveal/major_event)
            chapter_budget: 章节预算

        Returns:
            (score, violations)
        """
        violations: List[RhythmViolation] = []

        # 自动检测场景类型
        if scene_type == "auto":
            scene_type = self._detect_scene_type(text)

        # 根据场景类型检查节奏
        if scene_type == "action":
            violations.extend(self._check_action_rhythm(text))
        elif scene_type == "reveal":
            violations.extend(self._check_reveal_rhythm(text))
        elif scene_type == "major_event":
            violations.extend(self._check_major_event_rhythm(text))

        if not violations:
            return 1.0, []

        total_penalty = sum(v.severity for v in violations)
        score = max(0.0, 1.0 - total_penalty * 0.15)

        return score, violations

    def _detect_scene_type(self, text: str) -> str:
        """自动检测场景类型"""
        action_count = sum(1 for kw in self.ACTION_KEYWORDS if kw in text)
        reveal_count = sum(1 for kw in self.REVEAL_KEYWORDS if kw in text)
        major_count = sum(1 for kw in self.MAJOR_EVENT_KEYWORDS if kw in text)

        scores = {
            "action": action_count,
            "reveal": reveal_count * 1.5,
            "major_event": major_count * 2,
        }

        if max(scores.values()) == 0:
            return "default"

        return max(scores, key=scores.get)

    def _check_action_rhythm(self, text: str) -> List[RhythmViolation]:
        """打斗场景节奏检查：应该简洁、动词密集"""
        violations = []

        # 检查句子长度
        sentences = re.split(r'[。！？\n]', text)
        long_sentences = [s for s in sentences if len(s) > 40]

        if len(long_sentences) > len(sentences) * 0.3:
            violations.append(RhythmViolation(
                violation_type="action_bloat",
                severity=0.6,
                description=f"打斗场景中{len(long_sentences)}句过长(>40字)，应更简洁",
                suggestion="打斗场景用短句：动作→结果→反应，每句不超过30字",
            ))

        # 检查形容词比例
        adj_count = len(re.findall(r'的[\u4e00-\u9fff]{1,3}', text))
        verb_count = len(re.findall(r'[\u4e00-\u9fff](了|着|过)', text))

        if adj_count > verb_count * 0.5 and verb_count > 3:
            violations.append(RhythmViolation(
                violation_type="action_bloat",
                severity=0.5,
                description="打斗场景形容词过多，动词密度不够",
                suggestion="用动词替代形容词：不要'快速的攻击'，而是'剑锋破空而至'",
            ))

        return violations

    def _check_reveal_rhythm(self, text: str) -> List[RhythmViolation]:
        """揭秘场景节奏检查：应该放慢、有铺垫"""
        violations = []

        # 检查揭秘是否太仓促
        reveal_pos = -1
        for kw in self.REVEAL_KEYWORDS:
            pos = text.find(kw)
            if pos >= 0:
                reveal_pos = pos
                break

        if reveal_pos >= 0:
            # 揭秘前的铺垫字数
            lead_in = text[:reveal_pos]
            if len(lead_in) < 50:
                violations.append(RhythmViolation(
                    violation_type="reveal_rush",
                    severity=0.7,
                    description="揭秘场景缺乏铺垫，真相来得太突然",
                    suggestion="揭秘前应有50字以上的情绪铺垫：犹豫、挣扎、回忆",
                ))

        return violations

    def _check_major_event_rhythm(self, text: str) -> List[RhythmViolation]:
        """大事件节奏检查：精准、不加冗余"""
        violations = []

        # 检查是否有无关描写
        daily_keywords = ["喝茶", "闲聊", "漫步", "赏花", "下棋", "午睡"]
        daily_count = sum(1 for kw in daily_keywords if kw in text)

        major_count = sum(1 for kw in self.MAJOR_EVENT_KEYWORDS if kw in text)

        if daily_count > 0 and major_count > 0:
            violations.append(RhythmViolation(
                violation_type="event_detour",
                severity=0.5,
                description="大事件场景中出现了日常描写，影响节奏",
                suggestion="大事件场景应聚焦核心事件，日常描写放到过渡段落",
            ))

        return violations
