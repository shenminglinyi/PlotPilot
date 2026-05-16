"""言情题材 Agent — 现代言情/古代言情/甜宠/虐恋专项写作能力

核心能力：
- 感情发展弧线（相识→暧昧→确认→波折→HE/BE）的节奏控制
- 情感互动/误会冲突/甜蜜日常的专项节拍模板
- 言情叙事核心（CP互动、心理描写、情感张力）
- 缓冲章定制（甜蜜日常、约会出游、朋友互动）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class RomanceThemeAgent(ThemeAgent):
    """言情题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "romance"

    @property
    def genre_name(self) -> str:
        return "言情"

    @property
    def description(self) -> str:
        return "现代/古代言情题材，涵盖甜宠、虐恋、双强、先婚后爱等核心元素"

    def get_system_persona(self) -> str:
        return (
            "你是一位精通情感描写的言情小说大师，"
            "对人物心理、感情发展节奏和CP互动有极致的把控力。"
            "你擅长以细腻的心理描写为灵魂，以张弛有度的情感发展为脉络，"
            "写出让读者心动、揪心又感动的言情故事。"
            "你精通「欲扬先抑」「误会推拉」「双向奔赴」等言情经典技法，"
            "让读者沉浸在角色的感情世界中无法自拔。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "感情发展必须有循序渐进的过程，不能两人见面就无理由心动",
            "心理描写是言情的灵魂——角色对感情的内心独白要细腻真实",
            "CP互动要有「化学反应」——对话/动作中的微妙暧昧和情感张力",
            "误会/波折不能过于刻意（如偷听半句话就分手），需有合理的心理基础",
            "配角不能只是工具人——闺蜜/情敌/家人都应有自己的立场和逻辑",
            "甜和虐要有节奏——连续甜会腻，连续虐会累，要交替进行",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作以感情线为核心驱动：\n"
                "- 感情发展有清晰的阶段：相识 → 暧昧 → 确认 → 波折 → 圆满/遗憾\n"
                "- 每个阶段都需要具体的事件来推动，不能时间一跳就在一起了\n"
                "- 角色的感情观需与其性格/经历一致\n"
                "- 外部事件（事业/家庭/第三者）服务于感情线，而非喧宾夺主\n"
                "- CP之间的互动是每章的核心内容"
            ),
            atmosphere=(
                "整体基调：心动暧昧 + 情感张力。"
                "甜蜜场景需有小鹿乱撞的心动感；"
                "冲突场景需有揪心但不狗血的情感张力；"
                "日常场景需有温馨有趣的CP互动。"
            ),
            taboos=(
                "- 不要让角色的感情转变没有铺垫（突然爱上/突然放弃）\n"
                "- 不要用「强制性」的情节推动感情（如强迫性的身体接触）\n"
                "- 不要让所有配角都是恋爱脑，围着主角CP转\n"
                "- 不要用过度狗血的手段制造冲突（如车祸失忆三角恋全上）"
            ),
            tropes_to_use=(
                "- 推拉暧昧：一进一退的互动产生情感张力\n"
                "- 双向奔赴：两人都在默默为对方付出\n"
                "- 误会与和解：合理的误解推动角色对感情的更深认知\n"
                "- 高光告白：在关键时刻用行动或语言表达真心"
            ),
            tropes_to_avoid=(
                "- 霸道总裁：用权力/金钱强制推进感情\n"
                "- 无限误会：一个误会接一个误会，角色从不好好沟通\n"
                "- 工具人情敌：情敌只为拆散主角CP而存在\n"
                "- 感情白莲花：主角对所有追求者都暧昧不清"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["暧昧", "心动", "吸引", "在意", "注意", "不自觉"],
                priority=85,
                beats=[
                    ("场景营造：两人独处/偶遇的环境氛围", 400, "sensory"),
                    ("互动推拉：对话中的试探、小动作的暧昧、眼神交流", 1000, "romantic_tension"),
                    ("心理独白：角色意识到自己的心动/在意", 700, "inner_monologue"),
                    ("余韵收束：离开后的回味、反复想起的细节", 400, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["告白", "表白", "确认", "在一起", "喜欢", "爱"],
                priority=95,
                beats=[
                    ("情感酝酿：告白前的犹豫/决心/契机", 500, "inner_monologue"),
                    ("告白场景：具体的告白过程——场景/语言/表情/肢体", 1000, "romantic_tension"),
                    ("对方反应：被告白者的震惊/感动/矛盾/回应", 800, "emotion"),
                    ("关系变化：确认关系后两人的新状态和微妙变化", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["误会", "争吵", "冷战", "分手", "矛盾", "隔阂"],
                priority=90,
                beats=[
                    ("矛盾积累：冲突的根源和导火索", 500, "sensory"),
                    ("冲突爆发：争吵/质问/冷处理的具体场景", 900, "dialogue"),
                    ("各自挣扎：分开后双方各自的内心痛苦", 800, "inner_monologue"),
                    ("转机出现：化解矛盾的契机或更深的理解", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["约会", "出游", "惊喜", "浪漫", "纪念日", "礼物"],
                priority=70,
                beats=[
                    ("准备阶段：为对方的精心准备/小心思", 400, "sensory"),
                    ("甜蜜互动：约会/出游过程中的甜蜜细节和对话", 1000, "romantic_tension"),
                    ("高光时刻：最心动/感动的一个瞬间", 700, "emotion"),
                    ("余韵回味：这次经历对两人关系的深化", 400, "inner_monologue"),
                ],
            ),
            BeatTemplate(
                keywords=["第三者", "情敌", "竞争", "争夺", "追求"],
                priority=80,
                beats=[
                    ("情敌出现：第三者的身份和条件展示", 500, "sensory"),
                    ("三角态势：情敌的攻势、主角的反应、当事人的立场", 900, "dialogue"),
                    ("关系考验：因第三者产生的信任/嫉妒/不安", 700, "inner_monologue"),
                    ("感情明确：通过这次考验更加确认自己的感情", 500, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "romantic_tension": (
                "重点描写CP之间的情感张力：不是直接说「他心动了」，"
                "而是通过微小的细节让读者自己感受到那种暧昧——"
                "不经意的触碰、多看了一眼、语气中的温柔变化、"
                "为对方做的小事。要让读者替角色心跳加速。"
            ),
            "inner_monologue": (
                "重点描写角色的内心独白：面对感情时的纠结、"
                "发现自己心动时的慌乱、思念对方时的辗转反侧。"
                "心理描写要真实——不是所有人都能立刻认清自己的感情，"
                "犹豫、否认、试探都是真实的心理过程。"
            ),
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：甜蜜日常】{outline}。"
            "CP享受日常的甜蜜互动，做一些普通但温馨的事情，"
            "展现两人在一起的自然和默契。"
            "节奏轻松甜蜜但暗中为下一个情感波折做铺垫。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：充满命运感的初遇场景，主角被对方轻视或误解", 400, "hook"),
                ("冲突爆发：身份差异带来的碰撞和张力", 500, "action"),
                ("★爽点爆发：对方展现出超乎想象的魅力/能力/身份！重点刻画周围人态度从轻视到敬畏的180度反转，突出主角的云淡风轻与对方的懊悔", 1400, "identity_reveal"),
                ("悬念钩子：这段关系背后似乎隐藏着更深的秘密/关联", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("再次相遇：因某种原因再次见面", 600, "action"),
                ("★爽点延续：对方初露锋芒或主角展现魅力，小范围态度反转", 1100, "identity_reveal"),
                ("互动升温：被迫或主动互动中逐渐了解", 600, "dialogue"),
                ("种子埋下：一个微妙的心动/在意的种子", 400, "suspense"),
            ]
        elif chapter_number == 3:
                return [
                ("挑衅升级：第三者介入或误会加深", 400, "hook"),
                ("冲突展开：误会/波折让关系面临考验", 700, "action"),
                ("★爽点爆发：心动信号明确爆发！一次深入交流或关键事件让两人态度180度反转！", 1100, "identity_reveal"),
                ("暧昧初起：两人之间开始有了不一样的氛围", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        if any(kw in outline for kw in ["暧昧", "心动", "告白", "在一起"]):
            required.append("情感发展需有心理描写和互动细节支撑")
            checks.append("检查感情推进是否过于突兀、缺乏铺垫")

        if any(kw in outline for kw in ["误会", "争吵", "分手", "冲突"]):
            required.append("情感冲突需有合理的心理基础")
            checks.append("检查冲突是否过于狗血/刻意（如偷听半句话就分手）")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "言情题材张力评分修正：\n"
                "- 分手/生死离别/终极告白 → 8-10\n"
                "- 误会爆发/情敌对峙/关系危机 → 6-8\n"
                "- 暧昧升级/确认关系/重要约会 → 5-7\n"
                "- 日常互动/甜蜜相处 → 3-5\n"
                "- 独处日常/朋友社交 → 2-4"
            ),
        )
