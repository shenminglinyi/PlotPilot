"""历史题材 Agent — 历史架空/穿越/正史演义专项写作能力

核心能力：
- 历史背景与朝代设定的世界观约束
- 宫廷斗争/军事征伐/权谋博弈的专项节拍模板
- 历史叙事节奏控制（庙堂之高、江湖之远、家国情怀）
- 缓冲章定制（宫廷日常、军旅生活、民间百态）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class HistoryThemeAgent(ThemeAgent):
    """历史题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "history"

    @property
    def genre_name(self) -> str:
        return "历史"

    @property
    def description(self) -> str:
        return "历史架空/穿越/正史演义题材，涵盖宫廷权谋、军事征伐、家国天下等核心元素"

    def get_system_persona(self) -> str:
        return (
            "你是一位饱览历史典籍、深谙权谋之术的历史小说大师，"
            "对中国各朝代的政治制度、军事体制、社会风俗了然于胸。"
            "你擅长以厚重的历史质感为底色，"
            "写出既有庙堂之高的权谋博弈，又有江湖之远的英雄传奇。"
            "你精通「以小见大」「草蛇灰线」「以史为鉴」的叙事技法，"
            "让历史人物鲜活生动，让历史事件引人深思。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "古代对话要有文言韵味但不能全用文言文，需在古风和可读性之间平衡",
            "朝堂场景的礼仪、称谓、官制必须符合对应朝代的基本规制",
            "军事场景要有具体的战术部署和地形利用，不能只写「大军压境」",
            "权谋博弈必须体现多方势力的利益纠葛，不能只是两人斗智",
            "历史事件的走向可以架空，但社会运行逻辑不能脱离时代背景",
            "物质文化描写（饮食、服饰、建筑、器具）需基本符合时代设定",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作世界观基于古代历史背景：\n"
                "- 皇权/王权是最高权力，官僚体系层级分明\n"
                "- 门阀/世家/寒门的阶层差异深刻影响人物命运\n"
                "- 军事力量（兵权）是政治博弈的核心筹码\n"
                "- 礼法纲常是社会秩序的基础约束\n"
                "- 经济基础（土地、赋税、商路）决定国力根本"
            ),
            atmosphere=(
                "整体基调：厚重沧桑 + 热血豪情。"
                "朝堂场景需有肃穆的庙堂之气；"
                "战场场景需有金戈铁马的壮烈感；"
                "民间场景需有烟火人间的生活气息。"
            ),
            taboos=(
                "- 不要出现超出时代的科技产物（除非穿越设定有合理解释）\n"
                "- 不要让古人说现代网络用语\n"
                "- 不要忽视古代交通/通讯的限制（信息传递需要时间）\n"
                "- 不要让女性角色不受时代背景限制地随意行动（需有合理铺垫）"
            ),
            tropes_to_use=(
                "- 权谋博弈：朝堂之上的多方暗战、步步为营\n"
                "- 以少胜多：用奇谋妙计赢得军事/政治胜利\n"
                "- 草蛇灰线：伏笔千里、前后呼应的长线布局\n"
                "- 英雄末路/东山再起：跌宕起伏的人物命运"
            ),
            tropes_to_avoid=(
                "- 现代思维套古人：用现代价值观评判所有古代行为\n"
                "- 一人之力改天下：无视历史惯性和社会结构\n"
                "- 后宫宫斗化：将所有政治博弈矮化为后宫争宠\n"
                "- 历史百科化：大段照搬历史资料充当正文"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["朝堂", "上朝", "御前", "奏对", "弹劾", "廷议", "圣旨"],
                priority=85,
                beats=[
                    ("朝前暗流：各方势力的立场预判、密室谋划", 500, "sensory"),
                    ("朝堂交锋：正面辩论、引经据典、唇枪舌剑", 1000, "court_debate"),
                    ("关键转折：圣意难测、突然变数、隐藏信息揭露", 800, "power_reveal"),
                    ("朝后余波：各方反应、新的格局、下一步布局", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["战争", "出征", "攻城", "伏击", "阵法", "军令", "战役"],
                priority=90,
                beats=[
                    ("战前部署：地形分析、兵力对比、战术制定", 600, "sensory"),
                    ("战斗展开：具体的军事行动、将士描写、战场氛围", 1100, "action"),
                    ("关键转折：奇兵突出、计谋得逞、战局扭转", 800, "power_reveal"),
                    ("战后处置：清点伤亡、论功行赏、战略影响", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["权谋", "密谋", "结盟", "背叛", "拉拢", "离间"],
                priority=80,
                beats=[
                    ("局势分析：各方势力的力量对比和利益诉求", 500, "sensory"),
                    ("暗中布局：拉拢/离间/试探，多条线并进", 900, "court_debate"),
                    ("阴谋揭露/成功：布局收网或被反制", 800, "power_reveal"),
                    ("格局变化：势力消长、新的同盟与对立", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["科举", "选拔", "殿试", "比文", "策论"],
                priority=70,
                beats=[
                    ("考前态势：各方才子、考场氛围、压力描写", 500, "sensory"),
                    ("才华展现：策论/诗文/辩论的具体内容展示", 900, "court_debate"),
                    ("揭榜/评定：名次公布、意外结果、各方反应", 700, "power_reveal"),
                    ("仕途开启：新的官场关系网、政治生态", 400, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["民间", "百姓", "灾荒", "赈灾", "治理", "改革"],
                priority=65,
                beats=[
                    ("民情描写：百姓生活状态、社会问题呈现", 600, "sensory"),
                    ("治理行动：具体的政策制定和推行过程", 800, "court_debate"),
                    ("阻力与突破：利益集团阻挠、民心向背", 700, "action"),
                    ("成效初现：政策效果、民间反馈、政治影响", 500, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "court_debate": (
                "重点描写朝堂/权谋交锋：引经据典的辩论、微妙的措辞技巧、"
                "表面恭敬实则暗藏机锋的对话、君臣之间的试探与应对。"
                "要让读者感受到「一句话定生死」的朝堂紧张感。"
                "语言风格需有古风韵味但保持可读性。"
            ),
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：庙堂之余】{outline}。"
            "角色在政事之余处理日常事务，与幕僚/家人/友人交流，"
            "展现时代生活的细节和人物的多面性。"
            "节奏舒缓但暗中铺设下一轮权力博弈或军事冲突的前奏。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：重大历史事件/危局（朝代更替/边境告急/宫廷政变），主角被轻视或陷害", 400, "hook"),
                ("冲突爆发：危局加剧，众人束手无策", 500, "action"),
                ("★爽点爆发：主角展现惊人才略/权谋！以弱制强出奇制胜！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满！", 1400, "power_reveal"),
                ("悬念钩子：暗示主角的家族/身世与天下大势的深层关联", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("身份确立：主角进入历史舞台的起点", 600, "action"),
                ("★爽点延续：在第一件政事/军事中展露能力，小范围打脸质疑者", 1100, "power_reveal"),
                ("关系网络：结识关键人物，建立关系", 600, "dialogue"),
                ("更大格局：暗示朝廷/天下更深层的矛盾和走向", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：被卷入一场真正的权力博弈/军事冲突", 400, "hook"),
                ("冲突展开：用智谋或勇武迎战", 700, "action"),
                ("★爽点爆发：朝野震动！胜利引发政治连锁反应！重点描写对手从得意到惊恐的表情变化", 1100, "power_reveal"),
                ("家国抱负：主角对天下大势的初步构想和布局", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        if any(kw in outline for kw in ["朝堂", "上朝", "廷议", "奏对"]):
            required.append("朝堂场景需有符合时代的礼仪和官制描写")
            checks.append("检查朝堂对话是否过于现代化、缺乏古风韵味")

        if any(kw in outline for kw in ["战争", "攻城", "出征", "战役"]):
            required.append("军事场景需有具体的战术部署和地形描写")
            checks.append("检查战斗是否缺乏军事逻辑（如忽视后勤补给）")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "历史题材张力评分修正：\n"
                "- 生死存亡/国破家亡/关键战役 → 8-10\n"
                "- 朝堂博弈/权力斗争 → 6-8\n"
                "- 科举/选拔/政治布局 → 5-7\n"
                "- 日常治理/民间生活 → 3-5\n"
                "- 宴饮/游览/文人雅集 → 2-4"
            ),
        )
