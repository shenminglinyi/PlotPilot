"""武侠题材 Agent — 传统武侠/新武侠专项写作能力

核心能力：
- 江湖门派与武功体系的世界观约束
- 江湖恩怨/比武切磋/寻宝探秘的专项节拍模板
- 武侠叙事节奏控制（侠义精神、快意恩仇、武学境界）
- 缓冲章定制（游历山水、酒楼听书、疗伤练功）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class WuxiaThemeAgent(ThemeAgent):
    """武侠题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "wuxia"

    @property
    def genre_name(self) -> str:
        return "武侠"

    @property
    def description(self) -> str:
        return "传统武侠/新武侠题材，涵盖江湖恩怨、门派纷争、侠义精神等核心元素"

    def get_system_persona(self) -> str:
        return (
            "你是一位深谙武侠之道的小说大师，"
            "传承金庸之厚重、古龙之飘逸、梁羽生之典雅。"
            "你擅长以精妙的武功描写为筋骨，以快意恩仇的江湖故事为血肉，"
            "写出既有侠义精神又有人性深度的武侠故事。"
            "你精通「以武入道」「正邪辩证」「侠之大者」等武侠核心主题，"
            "让读者在刀光剑影中感受到武侠世界独有的浪漫与哲思。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "武打场景必须有具体的招式拆解和身法描写，不能只写「打了起来」",
            "内功/轻功/暗器的运用要有武学逻辑，不能随意突破物理极限",
            "江湖规矩（如武林盟主、华山论剑、六大门派）需保持一致",
            "侠义精神的体现要通过行动而非说教，「路见不平拔刀相助」要有具体场景",
            "武功修炼需有循序渐进的过程，不能看了本秘籍就天下无敌",
            "正邪双方都应有合理的行事逻辑，反派不能只是纯粹的恶",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作世界观基于武侠江湖：\n"
                "- 武功是核心实力，但内功修为 > 招式花哨\n"
                "- 门派/帮会有明确的势力范围和规矩\n"
                "- 武林有公认的排名体系（如天下十大高手）\n"
                "- 江湖规矩（不杀妇孺、一对一挑战、信义为重）是行为底线\n"
                "- 朝廷与江湖的关系是重要的权力张力来源"
            ),
            atmosphere=(
                "整体基调：侠骨柔情 + 快意恩仇。"
                "战斗场景需有刀光剑影的动态美感；"
                "江湖场景需有豪迈洒脱的武侠气质；"
                "情感场景需有含蓄内敛的古典美感。"
            ),
            taboos=(
                "- 不要出现超出武侠范畴的超自然力量（如飞天遁地、法术）\n"
                "- 不要让主角仅凭一本秘籍就跨越多个实力层级\n"
                "- 不要让江湖前辈全部沦为路人甲\n"
                "- 不要忽视武器/暗器的物理限制（如剑气不能劈山断岳）"
            ),
            tropes_to_use=(
                "- 仗剑行侠：路见不平、侠义之举引发连锁剧情\n"
                "- 比武论剑：高手过招的精彩对决和武学交流\n"
                "- 身世之谜：主角或关键人物的隐藏身世牵动全局\n"
                "- 武林大会：各路英雄汇聚、恩怨交织的经典场景"
            ),
            tropes_to_avoid=(
                "- 武力通胀：后期武功描写越来越夸张、失去武侠质感\n"
                "- 圣母侠客：主角对所有坏人都无限仁慈\n"
                "- 门派脸谱化：正派必正义、邪派必邪恶\n"
                "- 武功百科：大段列举招式名称但无实际描写"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["比武", "过招", "切磋", "挑战", "论剑", "对决"],
                priority=90,
                beats=[
                    ("对阵态势：双方背景、武功路数分析、江湖恩怨交代", 500, "sensory"),
                    ("试探交锋：招式拆解、内力比拼、武学理念碰撞", 900, "martial_arts"),
                    ("高潮对决：绝学对决、险象环生、胜负关键", 1000, "martial_arts"),
                    ("胜负余波：武学感悟、江湖声望变化、新的恩怨", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["门派", "帮会", "掌门", "叛变", "灭门", "内乱"],
                priority=80,
                beats=[
                    ("门派危机：内忧外患的具体呈现", 500, "sensory"),
                    ("内部博弈：各派系的立场和行动", 800, "dialogue"),
                    ("关键冲突：叛变/袭击/对抗的爆发", 900, "action"),
                    ("新秩序：门派格局重建或覆灭", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["寻宝", "秘籍", "宝藏", "藏宝图", "遗迹", "地宫"],
                priority=75,
                beats=[
                    ("线索发现：秘籍/宝图/遗言的获取和解读", 500, "sensory"),
                    ("寻觅过程：追踪线索、应对机关、各方势力争夺", 1000, "action"),
                    ("宝物现世：秘籍/宝物的发现和争夺高潮", 800, "martial_arts"),
                    ("获宝余波：武功增长、引来觊觎、江湖震动", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["复仇", "报仇", "血债", "灭门", "寻仇"],
                priority=85,
                beats=[
                    ("仇恨铺垫：回忆/调查仇恨的根源和经过", 600, "emotion"),
                    ("追踪仇人：一路追查、逐步接近、小规模交锋", 800, "action"),
                    ("正面对决：与仇人的最终对决、情感爆发", 1000, "martial_arts"),
                    ("仇后心境：复仇后的空虚/释然/新的人生选择", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["行侠", "仗义", "救人", "除恶", "镖局", "护送"],
                priority=65,
                beats=[
                    ("路遇不平：发现恶势力欺压百姓/行旅遭劫", 500, "sensory"),
                    ("侠义出手：出手相助的战斗过程", 800, "martial_arts"),
                    ("背后真相：发现事件背后有更大的阴谋", 700, "suspense"),
                    ("侠名远播：义举带来的声望和新的际遇", 400, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "martial_arts": (
                "重点描写武打场景：具体的招式名称和拆解、内力运用的体感、"
                "身法步法的动态描写、兵器碰撞的质感。"
                "要有武术的「画面感」——读者能在脑中构建出动作场景。"
                "避免只列招式名而无实际动作描写，也避免写成格斗游戏的数值对比。"
            ),
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：江湖行旅】{outline}。"
            "主角行走江湖，在客栈酒楼歇脚、与三教九流交往，"
            "练功悟武，享受江湖的自在生活。"
            "节奏舒缓但暗中铺设下一个江湖风波的前奏。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：一场精彩的武打对决或江湖变故，主角被轻视或陷入绝境", 400, "hook"),
                ("冲突爆发：对手嚣张至极，旁观者也不看好主角", 500, "action"),
                ("★爽点爆发：主角展露惊人武功或隐藏身份！以弱胜强出人意料的一击！重点描写对手的不可置信和旁观者的极度震惊。短促句子，情绪拉满！", 1400, "power_reveal"),
                ("悬念钩子：暗示主角身世或与某个江湖大秘密的关联", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("踏入江湖：主角正式进入更广阔的武林世界", 600, "action"),
                ("★爽点延续：第一场正式交锋中展露武功路数，小范围打脸", 1100, "power_reveal"),
                ("江湖人脉：结识关键人物（师长/挚友/对手/红颜）", 600, "dialogue"),
                ("门派风云：暗示武林中正在酝酿的大事", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：被卷入一场门派纷争或江湖恩怨", 400, "hook"),
                ("冲突展开：大展身手的战斗过程", 700, "action"),
                ("★爽点爆发：声名初起！在江湖中打脸震惊众人！重点描写对手从嚣张到惊恐的变化", 1100, "power_reveal"),
                ("更大的江湖：通过此事发现武林中更深层的暗流涌动", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        if any(kw in outline for kw in ["比武", "过招", "对决", "切磋"]):
            required.append("武打场景需有具体的招式拆解和身法描写")
            checks.append("检查武打是否只有招式名而无动作描写")

        if any(kw in outline for kw in ["门派", "掌门", "武林"]):
            required.append("门派场景需体现江湖规矩和武林生态")
            checks.append("检查门派描写是否过于脸谱化")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "武侠题材张力评分修正：\n"
                "- 生死对决/灭门大战/武林浩劫 → 8-10\n"
                "- 高手过招/门派冲突/寻仇复仇 → 6-8\n"
                "- 比武切磋/学艺练功/寻宝探秘 → 5-7\n"
                "- 行走江湖/侠义助人 → 3-5\n"
                "- 休憩疗伤/江湖闲话/酒楼听曲 → 2-4"
            ),
        )
