"""都市题材 Agent — 现代都市/职场/商战专项写作能力

核心能力：
- 现实社会背景的世界观约束（商业逻辑、职场规则、城市生活）
- 人际关系/职场博弈/商业谈判的专项节拍模板
- 都市爽文节奏控制（逆袭打脸、装逼社交、身份反转）
- 缓冲章定制（日常生活、社交聚会、情感升温）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class DushiThemeAgent(ThemeAgent):
    """都市题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "dushi"

    @property
    def genre_name(self) -> str:
        return "都市"

    @property
    def description(self) -> str:
        return "现代都市/职场/商战题材，涵盖逆袭打脸、商业博弈、都市情感等核心元素"

    # ─── 1. 人设 ───

    def get_system_persona(self) -> str:
        return (
            "你是一位深谙现代都市生活与商业逻辑的网络小说大师，"
            "熟悉职场竞争、商业运作、社交规则与城市文化。"
            "你擅长以真实可信的社会背景为舞台，"
            "写出既有爽感又接地气的都市故事。"
            "你精通「扮猪吃老虎」「身份反转」「商业逆袭」等经典都市套路的高级写法，"
            "让读者在熟悉的现实世界中获得代入感和满足感。"
        )

    # ─── 2. 写作规则 ───

    def get_writing_rules(self) -> List[str]:
        return [
            "商业谈判/博弈场景必须有具体的策略和逻辑推演，不能只靠主角气场碾压",
            "社交场景中的对话要符合现代都市人的说话方式，不要过于书面化或古风化",
            "涉及专业领域（金融、医学、法律等）时，关键术语和逻辑必须基本准确",
            "人际关系的发展要有铺垫和过程，不能让角色无理由地突然倒向主角",
            "打脸/逆袭场景要有前期蓄力（被轻视、被打压），反转才有爽感",
            "财富和地位的获取需有合理路径，不能天降横财解决所有问题",
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
                "本作世界观基于现代都市社会：\n"
                "- 社会规则（法律、商业、职场）是行为约束的底线\n"
                "- 人脉关系和社会资源是核心竞争力\n"
                "- 经济逻辑和商业规则必须基本自洽\n"
                "- 角色行为要符合其社会阶层和教育背景\n"
                "- 信息差和认知差是制造冲突的重要手段"
            ),
            atmosphere=(
                "整体基调：现实质感 + 逆袭爽感。"
                "商业场景需有紧张的博弈氛围；"
                "社交场景需有微妙的人情世故；"
                "日常场景可以轻松都市感但不能过于悬浮。"
            ),
            taboos=(
                "- 不要出现超自然能力（异能、修炼等），除非设定中明确允许\n"
                "- 不要让主角仅凭武力解决所有社会问题\n"
                "- 不要让配角的智商随剧情需要而剧烈波动\n"
                "- 不要让主角一夜暴富后就失去奋斗动力\n"
                "- 不要过度美化违法行为或灰色地带"
            ),
            tropes_to_use=(
                "- 身份反转：被看不起的小人物其实有惊人背景/能力\n"
                "- 商业博弈：信息战、人脉战、资源战的多层博弈\n"
                "- 社交打脸：在高端场合用实力/见识碾压装逼者\n"
                "- 逆袭成长：从底层一步步往上走，每次都让对手刮目相看"
            ),
            tropes_to_avoid=(
                "- 无脑种马：所有女性角色只为爱慕主角而存在\n"
                "- 万能系统：现代都市中突然出现玄幻式的金手指\n"
                "- 无限降智：对手全是纸老虎，毫无真正的威胁\n"
                "- 暴力万能：所有矛盾都靠打架解决"
            ),
        )

    # ─── 4. 节拍模板 ───

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            # 商业谈判/博弈场景
            BeatTemplate(
                keywords=["谈判", "商战", "博弈", "合作", "收购", "投资", "签约"],
                priority=85,
                beats=[
                    ("谈判前：双方底牌和诉求分析、场景氛围渲染", 500, "sensory"),
                    ("博弈过程：策略交锋、信息试探、筹码比拼、心理战", 1000, "negotiation"),
                    ("关键反转：隐藏信息揭露、局势逆转、对手措手不及", 800, "power_reveal"),
                    ("结局处理：协议达成/破裂、各方反应、后续影响", 500, "emotion"),
                ],
            ),
            # 社交打脸场景
            BeatTemplate(
                keywords=["打脸", "宴会", "聚会", "婚礼", "同学会", "嘲讽", "看不起"],
                priority=90,
                beats=[
                    ("场景铺设：社交场合描写、各方人物关系、潜在冲突", 500, "sensory"),
                    ("蓄力阶段：主角被轻视/嘲讽/排挤，对方嚣张得意", 700, "dialogue"),
                    ("身份/实力揭露：真实身份曝光或关键能力展现", 900, "identity_reveal"),
                    ("反转收场：嘲讽者惊愕、势利者讨好、主角淡然离场", 600, "emotion"),
                ],
            ),
            # 职场竞争场景
            BeatTemplate(
                keywords=["晋升", "竞聘", "项目", "汇报", "考核", "述职", "方案"],
                priority=75,
                beats=[
                    ("竞争态势：对手实力分析、各方站队、职场暗流", 500, "sensory"),
                    ("方案/能力展示：专业能力的具体呈现、数据和逻辑支撑", 900, "professional"),
                    ("暗中博弈：人脉运作、信息战、背后角力", 700, "negotiation"),
                    ("结果揭晓：胜负分明、新格局形成、下一步挑战预告", 500, "emotion"),
                ],
            ),
            # 危机处理场景
            BeatTemplate(
                keywords=["危机", "公关", "丑闻", "曝光", "诽谤", "陷害", "黑幕"],
                priority=80,
                beats=[
                    ("危机爆发：突发事件、舆论风暴、各方压力", 500, "sensory"),
                    ("应对部署：快速分析局势、制定反制策略、调动资源", 800, "professional"),
                    ("绝地反击：关键证据/人物出场、真相揭露、局势逆转", 900, "power_reveal"),
                    ("善后收场：危机化解、敌人受挫、声望提升", 500, "emotion"),
                ],
            ),
            # 感情发展场景
            BeatTemplate(
                keywords=["约会", "表白", "暧昧", "误会", "重逢", "分手"],
                priority=65,
                beats=[
                    ("情境营造：场景氛围、两人的微妙关系状态", 400, "sensory"),
                    ("互动过程：对话交锋、小动作描写、心理活动", 900, "dialogue"),
                    ("关键时刻：情感突破/误会产生/关系升级", 700, "emotion"),
                    ("余韵收束：两人关系新状态、内心波动、伏笔", 400, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "negotiation": (
                "重点描写谈判/博弈过程：双方的策略交锋、筹码比拼、"
                "微表情和肢体语言透露的信息、信息差的利用。"
                "要让读者感受到智力对决的紧张感，而不只是靠气势压人。"
            ),
            "identity_reveal": (
                "重点描写身份反转/揭露：从他人视角的震惊反应、"
                "之前的伏笔回收、社会地位差距的具体呈现。"
                "核心要义：读者要通过周围人的反应「看到」身份的分量。"
            ),
            "professional": (
                "重点描写专业能力展现：具体的方案/思路/操作，"
                "用行业术语但不堆砌，展现主角的真正实力而非空口白牙。"
                "避免模糊的「他提出了一个天才般的方案」式偷懒写法。"
            ),
        }

    # ─── 5. 缓冲章模板 ───

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：都市日常】{outline}。"
            "主角在忙碌之余享受都市生活，与朋友/恋人社交互动，"
            "展现角色的生活化一面。节奏舒缓但暗中铺垫下一个商业/社交挑战。"
        )

    # ─── 6. 开篇定制 ───

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：主角落魄处境展示（被开除/被退婚/被陷害），被轻视到极致", 400, "hook"),
                ("冲突爆发：对方嚣张得意，主角被逼入绝境", 500, "action"),
                ("★爽点爆发：第一次身份反转/实力展露！重点刻画周围人态度从轻视到敬畏的180度反转，突出主角的云淡风轻与对方的懊悔！", 1400, "identity_reveal"),
                ("悬念钩子：暗示主角背后还有更深的底牌/背景，读者急切期待下一次反转", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("新环境适应：主角进入新的社交/职场/商业圈子", 600, "action"),
                ("★爽点延续：在专业领域首次展现能力，小范围打脸质疑者", 1100, "identity_reveal"),
                ("人际网络：结识盟友/对手/爱慕者", 600, "dialogue"),
                ("暗流涌动：更大的对手/阴谋/机会在背后浮现", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：被正式纳入某个竞争/博弈，压力迫近", 400, "hook"),
                ("冲突展开：用智慧和资源迎战", 700, "action"),
                ("★爽点爆发：对手刮目相看！周围人对主角的态度发生明显转变！重点描写对手从得意到惊恐的表情变化", 1100, "identity_reveal"),
                ("格局展开：通过此战打开新的发展空间和更多可能性", 400, "suspense"),
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

        if any(kw in outline for kw in ["谈判", "商战", "博弈", "合作"]):
            required.append("商业场景需有具体的策略和逻辑推演")
            checks.append("检查谈判是否只靠气势碾压而无实质博弈")

        if any(kw in outline for kw in ["打脸", "聚会", "宴会", "社交"]):
            required.append("社交打脸需有充分的蓄力铺垫")
            checks.append("检查反转是否突兀、是否有前期被轻视的铺垫")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "都市题材张力评分修正：\n"
                "- 生死危机/重大商业决战 → 8-10\n"
                "- 谈判博弈/社交打脸 → 6-8\n"
                "- 职场竞争/方案比拼 → 5-7\n"
                "- 日常社交/感情发展 → 3-5\n"
                "- 纯日常/休闲/旅行 → 2-4"
            ),
        )
