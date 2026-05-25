"""FusionProfile — 混合题材的高优先级叙事合同。

ThemeAgent 仍负责单题材专业能力；FusionProfile 只描述两个题材相遇时
必须保住的市场承诺、主线边界和禁忌。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class NarrativeAxisLock:
    core_promise: str
    central_conflict: str
    false_mystery: str = ""
    true_mystery: str = ""
    forbidden_mainline_competitors: List[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        lines = [
            "【叙事主轴锁】",
            f"核心承诺：{self.core_promise}",
            f"中心冲突：{self.central_conflict}",
        ]
        if self.false_mystery:
            lines.append(f"表层谜团：{self.false_mystery}")
        if self.true_mystery:
            lines.append(f"真实谜团：{self.true_mystery}")
        if self.forbidden_mainline_competitors:
            lines.append(
                "不得抬成第一主线："
                + "；".join(self.forbidden_mainline_competitors)
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class CharacterFunctionLock:
    name: str
    faction: str
    narrative_function: str
    relation_to_axis: str
    allowed_turn: str = ""
    forbidden_behavior: str = ""

    def to_prompt_line(self) -> str:
        parts = [
            f"{self.name}：阵营={self.faction}",
            f"功能={self.narrative_function}",
            f"主轴关系={self.relation_to_axis}",
        ]
        if self.allowed_turn:
            parts.append(f"可转变={self.allowed_turn}")
        if self.forbidden_behavior:
            parts.append(f"禁止={self.forbidden_behavior}")
        return "；".join(parts)


@dataclass(frozen=True)
class FusionProfile:
    key: str
    label: str
    primary_theme_key: str
    secondary_theme_keys: List[str]
    market_track_label: str
    context_rules: str
    taboos: List[str]
    axis_lock: NarrativeAxisLock
    character_locks: List[CharacterFunctionLock] = field(default_factory=list)

    def to_context_text(self) -> str:
        lines = [
            f"【融合题材合同：{self.label}】",
            f"市场定位：{self.market_track_label}",
            f"主题材：{self.primary_theme_key}",
            "副题材：" + "、".join(self.secondary_theme_keys),
            self.context_rules.strip(),
            self.axis_lock.to_prompt_text(),
        ]
        if self.character_locks:
            lines.append("【角色功能锁】")
            lines.extend(lock.to_prompt_line() for lock in self.character_locks)
        if self.taboos:
            lines.append("【融合题材禁忌】")
            lines.extend(f"- {item}" for item in self.taboos)
        return "\n".join(line for line in lines if line)


_PROFILES: Dict[str, FusionProfile] = {
    "cyber_xianxia": FusionProfile(
        key="cyber_xianxia",
        label="赛博剑仙",
        primary_theme_key="xianxia",
        secondary_theme_keys=["scifi", "cyberpunk"],
        market_track_label="赛博修真 / 后人类仙侠 / 算法天道爽文",
        context_rules=(
            "本作不是普通星际副本，也不是把仙侠名词换成科技名词。"
            "灵气/剑意可被映射为算力、神经同步率、协议权限与量子场，"
            "但道心与剑意必须保留人的不可复制性。核心爽点来自越权、破限、"
            "公开骗局、以古典剑道反杀算法秩序。"
        ),
        axis_lock=NarrativeAxisLock(
            core_promise="冷铸证明剑宗所谓天道只是被篡改的算法，并以剑意绕过神经税。",
            central_conflict="无损耗修行公开后，剑宗垄断秩序是否崩塌。",
            false_mystery="递归病毒、恐怖存在、古战场封印可以误导角色和读者。",
            true_mystery="谁植入神经税，为什么现代修行体系建立在消耗修行者生命上。",
            forbidden_mainline_competitors=[
                "递归病毒/恐怖存在不得取代神经税成为第一主线",
                "古战场封印不得吞掉剑宗垄断与算法天道主轴",
            ],
        ),
        character_locks=[
            CharacterFunctionLock(
                name="拓跋尘",
                faction="黑市/上古幸存者后裔",
                narrative_function="情报商、旧真相守门人、反剑宗垄断盟友",
                relation_to_axis="推动无损耗修行证据公开",
                forbidden_behavior="不得无铺垫变成剑宗议会代表或剥夺主角权限的激进派",
            ),
            CharacterFunctionLock(
                name="南宫婳",
                faction="天枢剑宗刑堂",
                narrative_function="追猎者到怀疑者再到叛逆盟友",
                relation_to_axis="用忠诚撕裂证明剑宗秩序的腐坏",
                allowed_turn="必须经过证据冲击与忠诚代价后才能转向",
            ),
            CharacterFunctionLock(
                name="即墨寒",
                faction="剑宗议会保守派",
                narrative_function="神经税秩序维护者",
                relation_to_axis="代表算法天道垄断的既得利益",
                forbidden_behavior="不得过早解释全部真相或无代价退场",
            ),
        ],
        taboos=[
            "不要把剑意写成纯黑客技能树；剑意必须包含道心、取舍与不可复制的人格痕迹。",
            "不要让主角只靠奇遇被动升级；每次越权必须引发监控、通缉、权限封锁或关系代价。",
            "不要连续多章停在记忆投影或历史说明里，必须回到现实压迫和可见选择。",
        ],
    )
}


def get_fusion_profile(key: Optional[str]) -> Optional[FusionProfile]:
    if not key:
        return None
    return _PROFILES.get(str(key).strip())


def list_fusion_profiles() -> List[FusionProfile]:
    return list(_PROFILES.values())
