"""战力系统守恒服务。"""
from __future__ import annotations

from typing import Any, Optional


SYSTEM_GAME_STANDARD = """系统文 / 游戏文战力规范：
1. 战力来自明确资源：等级、属性、技能熟练度、装备、血脉、职业或系统任务奖励。
2. 升级必须有代价或条件：经验、冷却、材料、任务、风险、消耗、负面状态至少占一项。
3. 越级胜利必须解释机制：克制、环境、情报差、一次性底牌、队友配合或对方限制。
4. 数值只服务剧情，不得随章临时发明新规则；新系统必须先登记规则再生效。
5. Boss 与副本要有门槛、奖励和失败代价，避免无损刷级导致战力通胀。"""


DEFAULT_TIER_SCHEMA = """凡人/新手 < 入门/黑铁 < 熟练/青铜 < 精英/白银 < 统领/黄金 < 领主/铂金 < 传奇/钻石 < 超凡/史诗 < 神话"""


class PowerSystemService:
    """管理战力规则、角色战力档案和崩坏风险提示。"""

    def __init__(self, repository):
        self.repository = repository

    def get_overview(self, novel_id: str) -> dict[str, Any]:
        rules = self.repository.get_rules(novel_id)
        profiles = self.repository.list_profiles(novel_id)
        events = self.repository.list_events(novel_id, limit=30)
        warnings = self._build_warnings(rules, profiles, events)

        return {
            "novel_id": novel_id,
            "standard": SYSTEM_GAME_STANDARD,
            "rules": rules or self._default_rules(novel_id),
            "profiles": profiles,
            "recent_events": events,
            "warnings": warnings,
        }

    def upsert_rules(
        self,
        *,
        novel_id: str,
        genre_type: str = "system_game",
        tier_schema: str = "",
        core_rules: str = "",
        taboo_rules: str = "",
        escalation_rules: str = "",
    ) -> dict[str, Any]:
        return self.repository.upsert_rules(
            novel_id=novel_id,
            genre_type=genre_type or "system_game",
            tier_schema=tier_schema or DEFAULT_TIER_SCHEMA,
            core_rules=core_rules or SYSTEM_GAME_STANDARD,
            taboo_rules=taboo_rules or "禁止无代价越级、禁止临时新增隐藏规则、禁止同阶数值忽高忽低。",
            escalation_rules=escalation_rules or "每次大升级必须有铺垫、代价、验证战与后遗症记录。",
        )

    def upsert_profile(
        self,
        *,
        novel_id: str,
        character_name: str,
        tier: str = "",
        rank_score: int = 0,
        abilities: str = "",
        limitations: str = "",
        growth_stage: str = "",
        last_verified_chapter: Optional[int] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        return self.repository.upsert_profile(
            novel_id=novel_id,
            character_name=character_name.strip(),
            tier=tier.strip(),
            rank_score=int(rank_score),
            abilities=abilities.strip(),
            limitations=limitations.strip(),
            growth_stage=growth_stage.strip(),
            last_verified_chapter=last_verified_chapter,
            notes=notes.strip(),
        )

    def create_event(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        character_name: str,
        event_type: str = "battle",
        opponent: str = "",
        outcome: str = "",
        power_delta: int = 0,
        evidence: str = "",
    ) -> dict[str, Any]:
        return self.repository.create_event(
            novel_id=novel_id,
            chapter_number=int(chapter_number),
            character_name=character_name.strip(),
            event_type=event_type.strip() or "battle",
            opponent=opponent.strip(),
            outcome=outcome.strip(),
            power_delta=int(power_delta),
            evidence=evidence.strip(),
        )

    @staticmethod
    def _default_rules(novel_id: str) -> dict[str, Any]:
        return {
            "id": "",
            "novel_id": novel_id,
            "genre_type": "system_game",
            "tier_schema": DEFAULT_TIER_SCHEMA,
            "core_rules": SYSTEM_GAME_STANDARD,
            "taboo_rules": "禁止无代价越级、禁止临时新增隐藏规则、禁止同阶数值忽高忽低。",
            "escalation_rules": "每次大升级必须有铺垫、代价、验证战与后遗症记录。",
            "created_at": "",
            "updated_at": "",
        }

    def _build_warnings(
        self,
        rules: Optional[dict[str, Any]],
        profiles: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []

        if not rules:
            warnings.append({
                "severity": "warning",
                "title": "尚未固化战力规则",
                "message": "建议先保存境界/等级表、升级代价和禁忌规则，否则系统文或游戏文后期容易临时加设定。",
            })
        else:
            for key, title in (
                ("tier_schema", "境界/等级表为空"),
                ("core_rules", "核心战力规则为空"),
                ("taboo_rules", "禁忌规则为空"),
            ):
                if not str(rules.get(key) or "").strip():
                    warnings.append({
                        "severity": "warning",
                        "title": title,
                        "message": "请补齐后再让外部模型或自动生成大规模战斗章节。",
                    })

        for profile in profiles:
            if int(profile.get("rank_score") or 0) >= 80 and not str(profile.get("limitations") or "").strip():
                warnings.append({
                    "severity": "error",
                    "title": f"{profile.get('character_name')} 缺少高战力限制",
                    "message": "高战力角色必须登记弱点、消耗、冷却或行动约束，否则容易无解化。",
                })

        for event in events:
            delta = int(event.get("power_delta") or 0)
            evidence = str(event.get("evidence") or "")
            outcome = str(event.get("outcome") or "")
            if delta >= 3:
                warnings.append({
                    "severity": "error",
                    "title": f"第{event.get('chapter_number')}章战力跳升过快",
                    "message": f"{event.get('character_name')} 单次变化 +{delta}，建议补铺垫、代价或拆成多章成长。",
                })
            if ("胜" in outcome or "击败" in outcome) and delta >= 2 and not self._has_cost_marker(evidence):
                warnings.append({
                    "severity": "warning",
                    "title": f"第{event.get('chapter_number')}章疑似无代价越级",
                    "message": "胜利事件缺少代价/限制/克制说明，建议补充受伤、消耗、底牌或环境优势。",
                })

        return warnings[:12]

    @staticmethod
    def _has_cost_marker(text: str) -> bool:
        markers = ("代价", "消耗", "冷却", "受伤", "重伤", "反噬", "克制", "环境", "底牌", "队友", "限制", "失败")
        return any(marker in text for marker in markers)
