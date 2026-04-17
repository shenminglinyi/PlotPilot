"""修炼体系 Skill — 为修仙/玄幻题材提供修炼境界体系的上下文增强

示例 Skill 实现，演示 ThemeSkill 的使用方式。
可被玄幻（xuanhuan）和仙侠（xianxia）题材共享。
"""

from typing import List
from application.engine.theme.theme_agent import ThemeSkill


class CultivationSystemSkill(ThemeSkill):
    """修炼体系生成器 — 注入修炼境界参考到写作上下文"""

    @property
    def skill_key(self) -> str:
        return "cultivation_system"

    @property
    def skill_name(self) -> str:
        return "修炼体系"

    @property
    def skill_description(self) -> str:
        return "注入标准修炼境界参考（练气→筑基→…→大乘→渡劫），确保全书境界描写一致"

    # ─── 适用题材 ───

    @property
    def compatible_genres(self) -> List[str]:
        """声明此 Skill 适用的题材 genre_key 列表"""
        return ["xuanhuan", "xianxia"]

    # ─── 注入点实现 ───

    def on_context_build(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        existing_context: str,
    ) -> str:
        return (
            "修炼境界体系（由低到高）：\n"
            "练气期 → 筑基期 → 金丹期 → 元婴期 → "
            "化神期 → 合体期 → 大乘期 → 渡劫期\n"
            "每个大境界分初期/中期/后期/巅峰四个小阶段。\n"
            "突破大境界需要天劫/心魔/特殊机缘，不可随意跳级。\n"
            "请确保角色的境界描写前后一致，不要出现境界倒退或跳跃。"
        )

    def on_beat_enhance(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        if beat_focus == "cultivation" or "突破" in beat_description or "修炼" in beat_description:
            return (
                "修炼/突破场景增强提示：描写灵气在经脉中的具体流动路径、"
                "丹田/识海的变化、突破瓶颈时的身体反应和天地异象。"
                "参照上方境界体系确认当前角色的境界。"
            )
        return ""

    def on_audit_enhance(
        self,
        chapter_number: int,
        chapter_content: str,
        outline: str,
    ) -> List[str]:
        checks = []
        if any(kw in chapter_content for kw in ["突破", "晋升", "渡劫", "筑基", "金丹", "元婴"]):
            checks.append("检查境界描写是否与全书体系一致（不可跳级、不可倒退）")
        return checks
