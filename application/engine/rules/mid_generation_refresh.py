"""中段刷新策略 + 尾段增强 — Layer 5+6+7 动态干预。

核心机制：
- 中段刷新：当 AC 扫描器检测到 AI 味飙升时，注入刷新指令
- 尾段增强：对章节最后 2-3 段进行 AI 味专项净化
- 两者协同工作：中段防止偏移，尾段确保收束质量
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from application.engine.rules.stream_ac_scanner import StreamScanResult
from application.audit.services.cliche_scanner import ClicheHit

logger = logging.getLogger(__name__)


# ─── 中段刷新指令模板 ───

MID_GENERATION_REFRESH_TEMPLATES: Dict[str, str] = {
    "微表情过多": (
        "⚠️ 检测到微表情偏移\n"
        "修正指令：\n"
        "- 立即停止使用微表情（嘴角上扬/眼里闪过/指尖泛白等）\n"
        "- 改用完整姿态变化或让对白本身传递情绪\n"
        "- 下一段必须有感官锚点（温度/光线/声音/气味之一）\n"
        "- 检查角色状态锁是否仍然有效"
    ),
    "比喻过多": (
        "⚠️ 检测到比喻偏移\n"
        "修正指令：\n"
        "- 立即停止使用比喻（仿佛/宛如/犹如/好似等）\n"
        "- 改用此刻的体温、光线角度、衣料触感等感官细节\n"
        "- 下一段必须有具体的环境锚点\n"
        "- 让读者自己感受，不要替读者感受"
    ),
    "声线标签过多": (
        "⚠️ 检测到声线标签偏移\n"
        "修正指令：\n"
        "- 立即停止使用声线标签（低沉地说/语气冰冷/带着XX口吻等）\n"
        "- 改用对白本身的标点和断句表现语气\n"
        "- 下一段对白要有信息增量\n"
        "- 让读者从对白内容推断说话者的情绪"
    ),
    "情绪标签过多": (
        "⚠️ 检测到情绪标签偏移\n"
        "修正指令：\n"
        "- 立即停止使用直接情绪标签（他感到愤怒/她悲伤地/他开心地）\n"
        "- 改用动作暗示情绪（攥紧/松开/端起杯子又放下等）\n"
        "- 下一段要有环境对情绪的映射\n"
        "- 情绪通过感官和动作传递，不通过名词"
    ),
    "通用刷新": (
        "⚠️ 检测到AI味偏移\n"
        "修正指令：\n"
        "- 立即停止使用检测到的AI味模式\n"
        "- 改用感官细节+动作+对白的方式表达\n"
        "- 下一段必须有感官锚点\n"
        "- 不要重新写已经写过的内容，从最后一个有效段落之后继续"
    ),
}


class MidGenerationRefresh:
    """中段刷新策略。"""

    def __init__(self):
        self._templates = dict(MID_GENERATION_REFRESH_TEMPLATES)

    def detect_issue_category(self, scan_results: List[StreamScanResult]) -> str:
        """从扫描结果判断主要问题类别。"""
        category_counts: Dict[str, int] = {}
        for r in scan_results:
            cat = r.category or "其他"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if not category_counts:
            return "通用刷新"

        # 返回出现最多的类别
        top_category = max(category_counts, key=category_counts.get)

        category_to_template = {
            "微表情": "微表情过多",
            "声线": "声线标签过多",
            "比喻": "比喻过多",
            "情绪": "情绪标签过多",
        }

        return category_to_template.get(top_category, "通用刷新")

    def build_refresh_directive(
        self,
        scan_results: List[StreamScanResult],
    ) -> str:
        """构建中段刷新指令。

        Args:
            scan_results: AC 扫描结果

        Returns:
            刷新指令文本（注入到生成过程中）
        """
        issue_category = self.detect_issue_category(scan_results)
        template = self._templates.get(issue_category, self._templates["通用刷新"])

        # 补充具体的被禁止模式和替换模式
        forbidden_patterns = set()
        for r in scan_results:
            if r.severity == "critical":
                forbidden_patterns.add(r.pattern_name)

        if forbidden_patterns:
            template += f"\n\n具体被禁止的模式：{'、'.join(list(forbidden_patterns)[:5])}"

        return template

    def should_refresh(self, scan_results: List[StreamScanResult]) -> bool:
        """判断是否需要中段刷新。"""
        # 有 critical 级别匹配
        if any(r.severity == "critical" for r in scan_results):
            return True
        # 同一类别 3+ 次 warning
        category_counts: Dict[str, int] = {}
        for r in scan_results:
            if r.category:
                category_counts[r.category] = category_counts.get(r.category, 0) + 1
                if category_counts[r.category] >= 3:
                    return True
        return False


class FinaleEnhancer:
    """尾段增强策略。"""

    # 尾段 AI 味高频模式
    FINALE_AI_PATTERNS = [
        (r"一切才刚刚开始", "总结性金句", "改为动作/画面收束"),
        (r"有些(事情|东西)永远改变了", "总结性金句", "改为具体的变化表现"),
        (r"那天(晚上|下午|清晨)改变了.*命运", "命运总结", "改为角色的具体行为"),
        (r"他知道自己再也回不去了", "回不去金句", "改为角色此刻的动作"),
        (r"他感到一种.{0,6}的情绪", "情绪标签结尾", "改为感官细节"),
        (r"某种说不清的.{0,4}涌上", "模糊感受结尾", "改为具体的身体反应"),
        (r"——", "破折号悬念", "改为具体的未完成动作"),
    ]

    def enhance_finale(self, finale_text: str, expected_ending: str = "") -> str:
        """对章节尾段进行 AI 味净化。

        这是一个标记/建议功能，实际重写由 LLM 执行。
        这里返回净化建议。

        Args:
            finale_text: 章节最后 2-3 段
            expected_ending: 大纲预期的结尾走向

        Returns:
            净化建议文本
        """
        import re

        issues = []
        for pattern, name, suggestion in self.FINALE_AI_PATTERNS:
            if re.search(pattern, finale_text):
                issues.append(f"- {name}：{suggestion}")

        if not issues:
            return "尾段AI味检测通过，无需净化。"

        lines = [
            "━━━ 尾段AI味净化建议 ━━━",
            "",
            "检测到以下问题：",
        ]
        lines.extend(issues)
        lines.extend([
            "",
            "修正方向：",
            "1. 总结性金句 → 改为动作/画面收束（一个人转身走了、灯灭了、手机屏幕暗下去）",
            "2. 情绪标签结尾 → 改为感官细节（雨声更大了、咖啡凉了、远处传来关门声）",
            "3. 破折号悬念 → 改为具体的未完成动作（手停在门把手上、话说到一半、视线落在某处不动了）",
        ])

        if expected_ending:
            lines.append(f"\n大纲预期结尾走向：{expected_ending}")

        return "\n".join(lines)


# 全局单例
_mid_refresh: Optional[MidGenerationRefresh] = None
_finale_enhancer: Optional[FinaleEnhancer] = None

def get_mid_generation_refresh() -> MidGenerationRefresh:
    global _mid_refresh
    if _mid_refresh is None:
        _mid_refresh = MidGenerationRefresh()
    return _mid_refresh

def get_finale_enhancer() -> FinaleEnhancer:
    global _finale_enhancer
    if _finale_enhancer is None:
        _finale_enhancer = FinaleEnhancer()
    return _finale_enhancer
