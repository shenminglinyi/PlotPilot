"""情感节奏 Skill — 为言情/情感线提供甜虐节奏控制的增强

适用于言情题材及任何有重要感情线的题材。
"""

from typing import List
from application.engine.theme.theme_agent import ThemeSkill


class EmotionPacingSkill(ThemeSkill):
    """情感节奏控制器 — 控制甜虐交替、避免情感疲劳"""

    @property
    def skill_key(self) -> str:
        return "emotion_pacing"

    @property
    def skill_name(self) -> str:
        return "情感节奏"

    @property
    def skill_description(self) -> str:
        return "控制甜蜜/虐心的交替节奏，避免连续甜腻或连续虐心导致读者疲劳"

    @property
    def compatible_genres(self) -> List[str]:
        return ["romance"]

    def on_beat_enhance(
        self,
        beat_description: str,
        beat_focus: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        if beat_focus in ("romantic_tension", "inner_monologue", "emotion"):
            return (
                "情感节奏增强提示：\n"
                "1. 甜后埋刺：甜蜜场景结尾留一个微小的不安/隐患\n"
                "2. 虐中有暖：虐心场景中穿插对方默默付出的细节\n"
                "3. 心理真实：角色不会突然想通一切，犹豫和反复是真实的\n"
                "4. 感官描写：心动通过具体的身体反应呈现（心跳、脸红、不敢对视）"
            )
        return ""

    def on_audit_enhance(
        self,
        chapter_number: int,
        chapter_content: str,
        outline: str,
    ) -> List[str]:
        checks = []
        if any(kw in outline for kw in ["感情", "暧昧", "告白", "分手", "误会"]):
            checks.append("检查情感发展是否有过渡铺垫（不能突然心动或突然放弃）")
        return checks
