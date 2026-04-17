"""推理逻辑校验 Skill — 为悬疑/推理题材提供公平推理原则的增强

确保线索布置符合推理公平原则，关键证据在揭露前已出现。
"""

from typing import List
from application.engine.theme.theme_agent import ThemeSkill


class DeductionLogicSkill(ThemeSkill):
    """推理逻辑校验器 — 确保推理链完整、线索公平"""

    @property
    def skill_key(self) -> str:
        return "deduction_logic"

    @property
    def skill_name(self) -> str:
        return "推理逻辑"

    @property
    def skill_description(self) -> str:
        return "确保推理链条完整自洽、线索布置符合公平推理原则、红鲱鱼自然不刻意"

    @property
    def compatible_genres(self) -> List[str]:
        return ["suspense"]

    def on_context_build(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        existing_context: str,
    ) -> str:
        return (
            "推理公平原则检查清单：\n"
            "1. 每条关键线索必须在真相揭露前至少出现过一次\n"
            "2. 红鲱鱼必须有独立的合理解释，不能事后被无视\n"
            "3. 推理链：观察 → 假设 → 验证 → 排除 → 结论，不可跳步\n"
            "4. 凶手/真相的动机必须在前文有过暗示或铺垫\n"
            "5. 时间线、不在场证明等关键要素必须经得起回溯验证"
        )

    def on_audit_enhance(
        self,
        chapter_number: int,
        chapter_content: str,
        outline: str,
    ) -> List[str]:
        checks = []
        if any(kw in chapter_content for kw in ["真相", "揭露", "凶手", "破案", "推理"]):
            checks.append("检查揭露的真相是否在前文有充分的线索铺垫（公平原则）")
            checks.append("检查推理链是否有逻辑跳跃或缺失环节")
        return checks
