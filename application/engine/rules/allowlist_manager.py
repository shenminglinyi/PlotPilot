"""场景化白名单管理器 — Layer 3: 特定场景下的模式豁免。

核心逻辑：
- 在战斗/悬疑/恐怖/告白等特定场景中，部分"AI味"模式是被允许的
- 白名单不等于滥用，即使在允许场景中也有密度限制
- 默认场景(default)下所有模式都被禁止
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class AllowlistRule:
    """白名单规则。"""
    scene_type: str  # battle/suspense/horror/confession/revelation/default
    allowed_categories: Set[str]  # 允许的分类（如 {"微表情", "生理性"}）
    allowed_patterns: Set[str]  # 允许的具体模式名
    max_density_per_1000: float = 1.0  # 每千字最大出现次数
    description: str = ""


# ─── 预定义白名单规则 ───

PREDEFINED_ALLOWLIST: Dict[str, AllowlistRule] = {
    "default": AllowlistRule(
        scene_type="default",
        allowed_categories=set(),
        allowed_patterns=set(),
        max_density_per_1000=0.0,
        description="默认场景：所有AI味模式被禁止",
    ),
    "battle": AllowlistRule(
        scene_type="battle",
        allowed_categories={"生理性"},
        allowed_patterns={"心脏猛地一缩", "血液沸腾", "呼吸一窒"},
        max_density_per_1000=1.0,
        description="战斗场景：允许生理性描写（心跳/血压/肾上腺素），但禁止微表情和比喻",
    ),
    "suspense": AllowlistRule(
        scene_type="suspense",
        allowed_categories={"微表情"},
        allowed_patterns={"瞳孔微缩", "目光微动"},
        max_density_per_1000=0.5,
        description="悬疑场景：允许极少量微表情（瞳孔/目光），但禁止比喻和声线标签",
    ),
    "horror": AllowlistRule(
        scene_type="horror",
        allowed_categories={"生理性", "环境模板"},
        allowed_patterns={"呼吸一窒", "指尖冰凉", "空气凝固了"},
        max_density_per_1000=1.5,
        description="恐怖场景：允许生理恐惧反应和氛围描写，但禁止比喻和情绪标签",
    ),
    "confession": AllowlistRule(
        scene_type="confession",
        allowed_categories={"生理性", "微表情"},
        allowed_patterns={"心脏漏跳一拍", "指尖泛白", "嘴角抿起"},
        max_density_per_1000=1.0,
        description="告白场景：允许心跳加速和嘴唇微表情，但禁止比喻和总结性金句",
    ),
    "revelation": AllowlistRule(
        scene_type="revelation",
        allowed_categories={"生理性", "微表情"},
        allowed_patterns={"瞳孔骤缩", "呼吸一窒", "指尖泛白", "心脏猛地一缩"},
        max_density_per_1000=2.0,
        description="揭秘/反转场景：允许强烈的生理反应和瞳孔微表情，但禁止比喻和总结性金句",
    ),
}

# 场景类型中文映射
SCENE_TYPE_LABELS: Dict[str, str] = {
    "default": "默认",
    "battle": "战斗",
    "suspense": "悬疑",
    "horror": "恐怖",
    "confession": "告白",
    "revelation": "揭秘/反转",
}


class AllowlistManager:
    """场景化白名单管理器。"""

    def __init__(self):
        self._rules: Dict[str, AllowlistRule] = dict(PREDEFINED_ALLOWLIST)

    def get_rule(self, scene_type: str) -> AllowlistRule:
        """获取指定场景类型的白名单规则。"""
        return self._rules.get(scene_type, self._rules["default"])

    def is_allowed(self, scene_type: str, category: str, pattern_name: str) -> bool:
        """检查某个模式在指定场景中是否被允许。"""
        rule = self.get_rule(scene_type)
        # 分类级别允许
        if category in rule.allowed_categories:
            return True
        # 具体模式级别允许
        if pattern_name in rule.allowed_patterns:
            return True
        return False

    def get_allowed_patterns_text(self, scene_type: str) -> str:
        """获取允许的模式列表文本（注入到 Prompt）。"""
        rule = self.get_rule(scene_type)
        if not rule.allowed_categories and not rule.allowed_patterns:
            return "无（当前场景下所有AI味模式均被禁止）"
        parts = []
        if rule.allowed_categories:
            parts.append(f"分类豁免：{'、'.join(rule.allowed_categories)}")
        if rule.allowed_patterns:
            parts.append(f"具体模式豁免：{'、'.join(rule.allowed_patterns)}")
        parts.append(f"密度限制：每千字最多{rule.max_density_per_1000}次")
        return "\n".join(parts)

    def get_forbidden_patterns_text(self, scene_type: str) -> str:
        """获取仍然禁止的模式分类文本（注入到 Prompt）。"""
        rule = self.get_rule(scene_type)
        # 所有分类
        all_categories = {"微表情", "声线", "比喻", "生理性", "句式", "叙事", "环境", "节奏"}
        forbidden = all_categories - rule.allowed_categories
        if forbidden:
            return f"{'、'.join(sorted(forbidden))}（这些分类下的模式仍然被禁止）"
        return "无（注意密度限制）"

    def generate_allowlist_block(self, scene_type: str) -> str:
        """生成完整的白名单文本块（注入到 Prompt）。"""
        label = SCENE_TYPE_LABELS.get(scene_type, scene_type)
        rule = self.get_rule(scene_type)

        lines = [
            "━━━ 场景化豁免白名单 ━━━",
            f"",
            f"当前场景类型：{label}",
            f"",
            f"以下模式在本场景中被豁免（可以正常使用）：",
            self.get_allowed_patterns_text(scene_type),
            f"",
            f"以下模式仍然被禁止：",
            self.get_forbidden_patterns_text(scene_type),
            f"",
            f"注意：豁免不等于滥用。即使在允许的场景中，也要控制密度——同一模式每1000字最多出现{rule.max_density_per_1000}次。",
        ]
        return "\n".join(lines)

    def add_custom_rule(self, rule: AllowlistRule) -> None:
        """添加自定义白名单规则。"""
        self._rules[rule.scene_type] = rule
        logger.info("AllowlistManager: 已添加自定义规则 %s", rule.scene_type)

    def list_scene_types(self) -> List[str]:
        """列出所有场景类型。"""
        return list(self._rules.keys())


# 全局单例
_manager: Optional[AllowlistManager] = None


def get_allowlist_manager() -> AllowlistManager:
    """获取全局白名单管理器。"""
    global _manager
    if _manager is None:
        _manager = AllowlistManager()
    return _manager
