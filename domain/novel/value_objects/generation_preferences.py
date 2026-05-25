"""每本书的生成/全托管偏好（持久化于 novels.generation_prefs_json）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class GenerationPreferences:
    """全托管与节拍指挥相关偏好。"""

    # 工作台/全托管 UI：True 时叙事单元展示为「第 N 阶段」，否则为「章」（默认阶段）
    phase_display_mode: bool = True
    # 超出节拍硬上限时是否做 smart_truncate（关则按字符硬截断；关硬帽时本项无意义）
    smart_truncate_enabled: bool = False
    # 是否启用节拍字数硬帽（False 时 hard_cap=0，且不截断）
    beat_hard_cap_enabled: bool = False
    # 覆盖 ChapterConductor 阈值；None 表示用类默认
    conductor_converge_threshold: Optional[float] = None
    conductor_land_threshold: Optional[float] = None
    # 落盘前将段内碎片换行连片（逗号衔接）；默认关闭
    inline_prose_aggregation_enabled: bool = False
    # ── 章末审计 → 人工闸门（paused_for_review；与小说家「一章一停 / 硬伤打回」对齐）──
    # 每章审计通过后进入待审阅，点「恢复」再走下一章（全自动 auto_approve 模式仍会跳过闸门）
    pause_after_each_chapter_audit: bool = False
    # 叙事管线明确失败（narrative_sync_ok=False），或文风在有限次改写后仍低于阈值 → 停机待人（需结合上一项均为可选项）
    audit_pause_on_hard_fail: bool = False
    # Anti-AI 审计综合判定为「严重」时停机待人（仅当章节闸门开启相关项时与其它条件并列生效）
    audit_pause_on_anti_ai_severe: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> GenerationPreferences:
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            return cls()
        # 全空对象：视为采用当前类默认
        if len(raw) == 0:
            return cls()
        # 兼容旧库：键缺失时默认「阶段」；显式 false 仍为章
        if "phase_display_mode" not in raw:
            phase_display_mode = True
        else:
            phase_display_mode = bool(raw["phase_display_mode"])
        # 键缺失时默认关闭（与类默认一致）
        if "smart_truncate_enabled" not in raw:
            smart_truncate_enabled = False
        else:
            smart_truncate_enabled = bool(raw["smart_truncate_enabled"])
        if "beat_hard_cap_enabled" not in raw:
            beat_hard_cap_enabled = False
        else:
            beat_hard_cap_enabled = bool(raw["beat_hard_cap_enabled"])
        conv = raw.get("conductor_converge_threshold")
        land = raw.get("conductor_land_threshold")
        converge: Optional[float]
        land_v: Optional[float]
        try:
            converge = float(conv) if conv is not None else None
        except (TypeError, ValueError):
            converge = None
        try:
            land_v = float(land) if land is not None else None
        except (TypeError, ValueError):
            land_v = None
        if converge is not None and not 0.0 < converge < 1.0:
            converge = None
        if land_v is not None and not 0.0 < land_v <= 1.0:
            land_v = None
        # 新键：缺省为关闭（不向旧库突然改变落盘形态）
        if "inline_prose_aggregation_enabled" not in raw:
            inline_prose_aggregation_enabled = False
        else:
            inline_prose_aggregation_enabled = bool(raw["inline_prose_aggregation_enabled"])
        # 章末闸门：旧库缺失键时默认为 False（不突然改变全自动行为）
        pause_after_each_chapter_audit = bool(raw.get("pause_after_each_chapter_audit", False))
        audit_pause_on_hard_fail = bool(raw.get("audit_pause_on_hard_fail", False))
        audit_pause_on_anti_ai_severe = bool(raw.get("audit_pause_on_anti_ai_severe", False))
        return cls(
            phase_display_mode=phase_display_mode,
            smart_truncate_enabled=smart_truncate_enabled,
            beat_hard_cap_enabled=beat_hard_cap_enabled,
            conductor_converge_threshold=converge,
            conductor_land_threshold=land_v,
            inline_prose_aggregation_enabled=inline_prose_aggregation_enabled,
            pause_after_each_chapter_audit=pause_after_each_chapter_audit,
            audit_pause_on_hard_fail=audit_pause_on_hard_fail,
            audit_pause_on_anti_ai_severe=audit_pause_on_anti_ai_severe,
        )

    @classmethod
    def from_json(cls, blob: Optional[str]) -> GenerationPreferences:
        if not blob or not str(blob).strip():
            return cls()
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(data)

    @classmethod
    def merge_patch(
        cls, base: GenerationPreferences, patch: Optional[Dict[str, Any]]
    ) -> GenerationPreferences:
        if not patch:
            return base
        d = base.to_dict()
        allowed = set(d.keys())
        for k, v in patch.items():
            if k in allowed:
                d[k] = v
        return cls.from_dict(d)
