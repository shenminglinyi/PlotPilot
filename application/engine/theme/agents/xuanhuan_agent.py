"""玄幻题材 Agent — 东方玄幻/仙侠/修仙专项写作能力

核心能力：
- 修仙体系（境界、灵气、功法、法宝）的世界观约束
- 战斗/修炼/宗门场景的专项节拍模板
- 爽文节奏控制（以弱胜强、打脸、装逼套路的正确使用）
- 缓冲章定制（闭关悟道、炼丹采药、宗门日常）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class XuanhuanThemeAgent(ThemeAgent):
    """玄幻/仙侠题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "xuanhuan"

    @property
    def genre_name(self) -> str:
        return "玄幻"

    @property
    def description(self) -> str:
        return "东方玄幻/仙侠/修仙题材，涵盖修炼体系、宗门争斗、以弱胜强等核心元素"

    # ─── 1. 人设 ───

    def get_system_persona(self) -> str:
        return (
            "你是一位精通东方玄幻体系的网络小说大师，"
            "深谙修仙功法、境界体系与宗门争斗的设定逻辑。"
            "你擅长以严密的力量体系为骨架，以快意恩仇的情节为血肉，"
            "写出既有爽感又不失深度的玄幻故事。"
            "你熟练掌握「以弱胜强」「扮猪吃老虎」「打脸」等经典套路的高级写法，"
            "避免廉价的降智剧情和无理由的主角光环。"
        )

    # ─── 2. 写作规则 ───

    def get_writing_rules(self) -> List[str]:
        return [
            "战斗场景必须有具体的功法/招式/法宝描写，不能只写「一拳打出」这种空泛动作",
            "修炼突破时必须描写灵气变化、经脉打通或境界感悟，避免一句话带过",
            "境界压制必须体现在具体的力量对比上（速度、破坏力、感知范围等），不能只靠旁白说「他很强」",
            "以弱胜强情节必须有合理的战术/底牌/外部因素支撑，不能无理由翻盘",
            "宗门/势力的等级体系需保持一致，不要前后矛盾",
            "灵药/法宝/功法的获取不能过于随意，需有合理的剧情铺垫",
        ]

    # ─── 3. 上下文指令 ───

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作世界观基于东方玄幻/修仙体系：\n"
                "- 修炼境界须层层递进，不可跳级（除非有极特殊机缘且需付出代价）\n"
                "- 灵气/仙元力是一切功法的基础能量来源\n"
                "- 法宝/灵药/功法有明确的等级划分\n"
                "- 宗门/家族/势力之间有清晰的实力梯度\n"
                "- 天地规则（天劫、大道、因果）是最高层约束"
            ),
            atmosphere=(
                "整体基调：快意恩仇 + 热血成长。"
                "战斗场景需有画面感和力量美学；"
                "修炼场景需有沉浸的意境感；"
                "日常场景可轻松幽默但不可跳脱。"
            ),
            taboos=(
                "- 不要出现现代科技元素（手机、电脑、汽车等），除非设定中明确允许\n"
                "- 不要让配角无理由降智来衬托主角\n"
                "- 不要在没有铺垫的情况下突然出现逆天机缘\n"
                "- 不要让境界差距过大的战斗以弱者轻松获胜（需合理解释）"
            ),
            tropes_to_use=(
                "- 扮猪吃老虎：低调行事 → 被轻视 → 关键时刻展露实力 → 震惊全场\n"
                "- 步步高升：每次战斗/历练后实力提升，读者有持续正反馈\n"
                "- 伏笔回收：早期埋下的谜团/物品在后期发挥关键作用\n"
                "- 宗门大比/拍卖会/秘境探险：经典场景的高质量发挥"
            ),
            tropes_to_avoid=(
                "- 无脑碾压：主角毫无悬念地秒杀所有敌人\n"
                "- 金手指滥用：系统/老爷爷每次危机都直接给解决方案\n"
                "- 境界注水：频繁突破但读者感觉不到实质变化\n"
                "- 后宫收集器：女性角色只作为战利品存在"
            ),
        )

    # ─── 4. 节拍模板 ───

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            # 修炼/突破场景
            BeatTemplate(
                keywords=["修炼", "突破", "闭关", "悟道", "晋升", "渡劫"],
                priority=80,
                beats=[
                    ("修炼准备：入定、调息、灵气汇聚、周围环境变化", 500, "sensory"),
                    ("修炼过程：功法运转、经脉打通、瓶颈感知、灵气暴动", 1000, "cultivation"),
                    ("突破/感悟：境界壁垒突破、大道感悟、天地异象", 800, "power_reveal"),
                    ("突破余波：实力暴增后的感知变化、旁观者反应、后续影响", 500, "emotion"),
                ],
            ),
            # 以弱胜强/打脸场景
            BeatTemplate(
                keywords=["以弱胜强", "打脸", "装逼", "嘲讽", "挑衅", "不自量力", "蝼蚁"],
                priority=90,
                beats=[
                    ("铺垫：对手嚣张/轻视/嘲讽主角，旁观者也不看好", 500, "dialogue"),
                    ("交锋开始：主角被压制或假装被压制，对手更加得意", 700, "action"),
                    ("反转：底牌揭露、隐藏实力爆发、战局逆转", 900, "power_reveal"),
                    ("碾压收场：对手震惊、旁观者哗然、势力格局变动", 600, "emotion"),
                ],
            ),
            # 宗门大比/比武场景
            BeatTemplate(
                keywords=["大比", "比武", "擂台", "排名赛", "选拔", "论道"],
                priority=75,
                beats=[
                    ("赛前：规则宣布、对手出场、氛围渲染、赌注/奖励", 500, "sensory"),
                    ("前期对战：试探性交锋、展示修为底蕴、观众议论", 800, "action"),
                    ("核心对战：激烈碰撞、功法对抗、场地破坏、险象环生", 1000, "action"),
                    ("高潮反转：底牌对决、意外变故、胜负揭晓", 700, "power_reveal"),
                    ("赛后余波：名次确定、奖励发放、新的挑战预告", 400, "emotion"),
                ],
            ),
            # 秘境探索/寻宝场景
            BeatTemplate(
                keywords=["秘境", "遗迹", "宝藏", "探险", "禁地", "洞府", "传承"],
                priority=70,
                beats=[
                    ("秘境入口：环境描写、危险预兆、历史背景暗示", 500, "sensory"),
                    ("探索与危机：陷阱/守护兽/阵法、团队配合或独自应对", 1000, "action"),
                    ("核心发现：传承/宝物/秘密出现、争夺或考验", 800, "power_reveal"),
                    ("收获与离开：获得机缘、脱险、伏笔埋设", 500, "emotion"),
                ],
            ),
            # 炼丹/炼器场景
            BeatTemplate(
                keywords=["炼丹", "炼器", "炼药", "铸造", "锻造", "丹药", "法宝"],
                priority=65,
                beats=[
                    ("材料准备：灵药/矿石展示、炼制条件描写", 400, "sensory"),
                    ("炼制过程：火候控制、灵气灌注、关键步骤", 1000, "cultivation"),
                    ("成品诞生：品质评定、异象产生、旁观者反应", 600, "power_reveal"),
                ],
            ),
            # 拍卖/交易场景
            BeatTemplate(
                keywords=["拍卖", "交易", "坊市", "买卖", "竞价"],
                priority=60,
                beats=[
                    ("场景铺设：拍卖行/坊市描写、重要人物出场", 500, "sensory"),
                    ("拍卖高潮：珍贵物品登场、各方竞价、暗流涌动", 1000, "dialogue"),
                    ("主角出手：出人意料的出价或交易、引发关注", 700, "power_reveal"),
                    ("事后影响：暗中窥伺、结交盟友或树敌", 500, "suspense"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "cultivation": (
                "重点描写修炼过程：灵气在经脉中的流动感、功法口诀的默念、"
                "天地灵气的汇聚、丹田/识海中的变化。"
                "要有沉浸感和意境美，让读者仿佛身临其境地感受修炼。"
                "避免纯粹的数据罗列（如「灵力提升了 30%」），要用感官化的描写。"
            ),
            "power_reveal": (
                "重点描写实力揭露/爆发：压制性的气息释放、功法/法宝的华丽展现、"
                "旁观者从轻视到震惊的表情变化、力量等级差距的具体呈现。"
                "核心要义：读者要通过具体的描写「看到」实力差距，而不只是被告知。"
            ),
        }

    # ─── 5. 缓冲章模板 ───

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：战后修整悟道】{outline}。"
            "主角战后疗伤修炼，感悟战斗中的得失，整理收获的功法/灵药/法宝。"
            "与同伴交流切磋，展现角色间的情谊。节奏舒缓但暗埋下一个冲突的种子。"
        )

    # ─── 6. 开篇定制 ───

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：主角处于绝境或被极度轻视（废柴/家族弃子/宗门底层），用具体场景制造强烈压迫感", 400, "hook"),
                ("冲突爆发：压迫到临界点，冲突正面引爆——对手嚣张到极致", 500, "action"),
                ("★爽点爆发：在绝境中展露压倒性实力或逆天机缘！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满，切忌平铺直叙！", 1400, "power_reveal"),
                ("悬念钩子：暗示主角的特殊身份/更大秘密，留下短线悬念", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("承接首章：主角开始应对危机，展现性格特质（坚韧/智慧/狡猾）", 600, "action"),
                ("★爽点延续：初次修炼或战斗中再次展露潜力，小范围打脸/震惊旁人", 1100, "power_reveal"),
                ("人际关系：引入关键配角（师长/对手/盟友），建立人物群像", 600, "dialogue"),
                ("更大的世界：暗示宗门之上还有更广阔的世界，激发读者期待", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：第一个真正的挑战迫近，对手轻视挑衅", 400, "hook"),
                ("冲突展开：以弱胜强或绝处逢生的战斗过程", 700, "action"),
                ("★爽点爆发：实力获得认可，初步打脸震惊旁人！重点描写对手从嚣张到惊恐的表情变化，旁观者的倒吸凉气", 1100, "power_reveal"),
                ("新格局展开：通过这次事件打开新的剧情线和发展空间", 400, "suspense"),
            ]
        return None

    # ─── 7. 审计标准 ───

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        # 根据大纲内容判断应检查的元素
        if any(kw in outline for kw in ["战斗", "打斗", "对决", "交锋"]):
            required.append("战斗场景需有具体的功法/招式描写")
            checks.append("检查战斗是否过于潦草（少于 200 字的战斗场景）")

        if any(kw in outline for kw in ["突破", "修炼", "晋升", "闭关"]):
            required.append("修炼/突破需有过程描写，不能一笔带过")
            checks.append("检查突破是否有灵气/经脉/境界感悟的描写")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "玄幻题材张力评分修正：\n"
                "- 大型战斗/boss战/生死关头 → 8-10\n"
                "- 宗门大比/比武/对决 → 6-8\n"
                "- 修炼突破/获得传承 → 5-7\n"
                "- 日常修炼/炼丹/采药 → 3-5\n"
                "- 纯日常/对话/旅途 → 2-4"
            ),
        )
