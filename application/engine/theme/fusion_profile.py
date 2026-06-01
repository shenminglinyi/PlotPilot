"""FusionProfile — 混合题材的高优先级叙事合同。

ThemeAgent 仍负责单题材专业能力；FusionProfile 只描述两个题材相遇时
必须保住的市场承诺、主线边界和禁忌。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import yaml


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


_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "taxonomy"
    / "fusion_profiles_cn_v1.yaml"
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _text_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


@lru_cache(maxsize=1)
def _load_profiles() -> Dict[str, FusionProfile]:
    data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    raw_profiles = data.get("profiles") if isinstance(data, dict) else {}
    profiles: Dict[str, FusionProfile] = {}
    if not isinstance(raw_profiles, dict):
        return profiles

    for raw_key, raw_profile in raw_profiles.items():
        if not isinstance(raw_profile, dict):
            continue
        key = _text(raw_key)
        axis = raw_profile.get("axis_lock") or {}
        if not key or not isinstance(axis, dict):
            continue
        character_locks = []
        for raw_lock in raw_profile.get("character_locks") or []:
            if not isinstance(raw_lock, dict):
                continue
            character_locks.append(
                CharacterFunctionLock(
                    name=_text(raw_lock.get("name")),
                    faction=_text(raw_lock.get("faction")),
                    narrative_function=_text(raw_lock.get("narrative_function")),
                    relation_to_axis=_text(raw_lock.get("relation_to_axis")),
                    allowed_turn=_text(raw_lock.get("allowed_turn")),
                    forbidden_behavior=_text(raw_lock.get("forbidden_behavior")),
                )
            )
        profiles[key] = FusionProfile(
            key=key,
            label=_text(raw_profile.get("label")),
            primary_theme_key=_text(raw_profile.get("primary_theme_key")),
            secondary_theme_keys=_text_list(raw_profile.get("secondary_theme_keys")),
            market_track_label=_text(raw_profile.get("market_track_label")),
            context_rules=_text(raw_profile.get("context_rules")),
            axis_lock=NarrativeAxisLock(
                core_promise=_text(axis.get("core_promise")),
                central_conflict=_text(axis.get("central_conflict")),
                false_mystery=_text(axis.get("false_mystery")),
                true_mystery=_text(axis.get("true_mystery")),
                forbidden_mainline_competitors=_text_list(
                    axis.get("forbidden_mainline_competitors")
                ),
            ),
            character_locks=character_locks,
            taboos=_text_list(raw_profile.get("taboos")),
        )
    return profiles


def get_fusion_profile(key: Optional[str]) -> Optional[FusionProfile]:
    if not key:
        return None
    return _load_profiles().get(str(key).strip())


def list_fusion_profiles() -> List[FusionProfile]:
    return list(_load_profiles().values())
