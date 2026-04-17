"""战斗编排 Skill — 为战斗场景提供招式/节奏编排的增强

适用于武侠、玄幻、仙侠、奇幻等包含战斗场景的题材。
"""

from typing import List
from application.engine.theme.theme_agent import ThemeSkill


class BattleChoreographySkill(ThemeSkill):
    """战斗编排器 — 增强战斗场景的动作描写质量"""

    @property
    def skill_key(self) -> str:
        return "battle_choreography"

    @property
    def skill_name(self) -> str:
        return "战斗编排"

    @property
    def skill_description(self) -> str:
        return "增强战斗场景的招式拆解、节奏控制和画面感，避免「他一拳打去」式的空泛描写"

    @property
    def compatible_genres(self) -> List[str]:
        return ["xuanhuan", "xianxia", "wuxia", "fantasy"]

    def on_beat_enhance(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        if beat_focus in ("action", "martial_arts", "power_reveal") or \
           any(kw in beat_description for kw in ["战斗", "对决", "交锋", "过招", "攻击"]):
            return (
                "战斗编排增强提示：\n"
                "1. 动作分解：将一个回合拆成「起手→出招→碰撞→结果」四拍\n"
                "2. 感官层次：视觉（招式形态）+ 听觉（破空声）+ 触觉（力量反馈）\n"
                "3. 节奏控制：快慢交替——密集对攻后穿插喘息/对话/心理\n"
                "4. 避免流水账：不要逐招列举，抓住 2-3 个关键招式重点描写\n"
                "5. 旁观者视角：穿插围观者的反应来侧面烘托战斗激烈程度"
            )
        return ""

    def on_audit_enhance(
        self,
        chapter_number: int,
        chapter_content: str,
        outline: str,
    ) -> List[str]:
        checks = []
        if any(kw in outline for kw in ["战斗", "对决", "比武", "交锋", "攻击"]):
            checks.append("检查战斗场景是否有具体的招式/动作描写（不能只有结果没有过程）")
            checks.append("检查战斗节奏是否有快慢变化（避免全程高强度或全程平淡）")
        return checks
