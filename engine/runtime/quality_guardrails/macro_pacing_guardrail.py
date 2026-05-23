"""Macro pacing guardrail.

This complements plot density: density catches too little story movement, while
macro pacing catches the opposite failure mode: opening chapters resolving too
many structural debts too cleanly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class MacroPacingViolation:
    violation_type: str
    severity: float
    description: str
    suggestion: str


class MacroPacingGuardrail:
    """Heuristic guardrail for early-payoff and over-resolution risks."""

    EARLY_CHAPTER_LIMIT = 12

    _RE_FULL_RESOLUTION = re.compile(
        r"(彻底|完全|当场|终于|真相大白|昭雪|平反|恢复(?:了)?身份|逐出宗门|废去修为|案件作罢)"
    )
    _RE_AUTHORITY_RESCUE = re.compile(r"(宗主|掌门|城主|长老会|执法堂).*?(亲临|裁决|宣布|作证|平反)")
    _RE_MAJOR_SECRET = re.compile(r"(失传|核心长老|神识烙印|真凶|幕后|身份|本命|仙体|天道|灵根)")
    _RE_ANTAGONIST_EXIT = re.compile(r"(真凶|长老|靠山|敌人|对手|谷梁|西门).*?(逃|跪|废|逐出|认输|败露)")

    def check(
        self,
        text: str,
        chapter_goal: str = "",
        scene_info: Dict[str, Any] | None = None,
    ) -> Tuple[float, List[MacroPacingViolation]]:
        body = text or ""
        chapter_number = self._chapter_number(chapter_goal, scene_info)
        if len(body.strip()) < 80:
            return 1.0, []

        violations: List[MacroPacingViolation] = []
        resolution_hits = len(self._RE_FULL_RESOLUTION.findall(body))
        authority_hits = len(self._RE_AUTHORITY_RESCUE.findall(body))
        secret_hits = len(self._RE_MAJOR_SECRET.findall(body))
        antagonist_hits = len(self._RE_ANTAGONIST_EXIT.findall(body))

        if chapter_number and chapter_number <= self.EARLY_CHAPTER_LIMIT:
            if resolution_hits >= 3 or (resolution_hits >= 2 and authority_hits >= 1):
                violations.append(
                    MacroPacingViolation(
                        violation_type="early_full_resolution",
                        severity=0.22,
                        description="开篇章节出现过多终局式解决信号，主线债务可能被提前结清",
                        suggestion="保留证据缺口、代价或反噬；把平反/昭雪拆成阶段性胜利",
                    )
                )
            if secret_hits >= 3 and resolution_hits >= 1:
                violations.append(
                    MacroPacingViolation(
                        violation_type="reveal_overload",
                        severity=0.16,
                        description="重大秘密与解决动作同章密集出现，读者期待缓冲不足",
                        suggestion="同章只揭一层秘密，其余改成误导、疑点或未验证线索",
                    )
                )
            if antagonist_hits >= 2 and resolution_hits >= 1:
                violations.append(
                    MacroPacingViolation(
                        violation_type="antagonist_exits_too_cleanly",
                        severity=0.14,
                        description="对抗方在早期过快败退或出局，后续压力源可能塌陷",
                        suggestion="让对手付出局部代价但保留反扑资源、同盟或未公开筹码",
                    )
                )
        elif resolution_hits >= 5 and secret_hits >= 6:
            violations.append(
                MacroPacingViolation(
                    violation_type="macro_payoff_congestion",
                    severity=0.12,
                    description="单章解决与揭秘信号过密，可能形成主线拥堵",
                    suggestion="把部分结果延后到下一章，用余波、代价或新问题承接",
                )
            )

        penalty = min(0.36, sum(v.severity for v in violations))
        return max(0.0, 1.0 - penalty), violations

    @staticmethod
    def _chapter_number(chapter_goal: str, scene_info: Dict[str, Any] | None) -> int | None:
        if scene_info:
            for key in ("chapter_number", "chapter", "number"):
                value = scene_info.get(key)
                try:
                    if value is not None:
                        return int(value)
                except (TypeError, ValueError):
                    pass
        m = re.search(r"第\s*(\d+)\s*章", chapter_goal or "")
        if m:
            return int(m.group(1))
        return None
