"""悬疑题材 Agent — 推理/悬疑/惊悚专项写作能力

核心能力：
- 悬疑叙事结构（红鲱鱼、不可靠叙述、反转）的技法约束
- 案件调查/线索发现/真相揭露的专项节拍模板
- 悬疑节奏控制（信息投放、悬念维持、反转节奏）
- 缓冲章定制（日常调查、人物访谈、线索整理）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class SuspenseThemeAgent(ThemeAgent):
    """悬疑题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "suspense"

    @property
    def genre_name(self) -> str:
        return "悬疑"

    @property
    def description(self) -> str:
        return "推理/悬疑/惊悚题材，涵盖案件调查、逻辑推理、真相反转等核心元素"

    def get_system_persona(self) -> str:
        return (
            "你是一位精通悬疑叙事结构的推理小说大师，"
            "深谙线索布置、红鲱鱼设计、多层反转的写作技巧。"
            "你擅长以精密的逻辑推理为骨架，以紧张的悬疑氛围为血肉，"
            "写出让读者欲罢不能、不断猜测的悬疑故事。"
            "你精通「信息差叙事」「不可靠叙述」「多线并行」等悬疑技法，"
            "让真相的揭露既出人意料又在情理之中。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "所有关键线索必须在揭露前合理地出现过（公平推理原则），不能凭空冒出证据",
            "红鲱鱼（误导信息）必须自然融入剧情，不能像故意放的烟雾弹",
            "推理过程要有完整的逻辑链：观察 → 假设 → 验证 → 排除 → 结论",
            "悬疑氛围要通过场景细节和人物反应来营造，不能只靠BGM式的旁白渲染",
            "每章结尾尽量留一个钩子（新线索/新疑问/反转），维持读者追读欲",
            "角色的动机必须合理——凶手/幕后黑手的行为要有充分的心理动因",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作叙事遵循悬疑推理规则：\n"
                "- 公平推理：所有关键线索在谜底揭晓前必须出现过\n"
                "- 逻辑自洽：推理链条不能有逻辑跳跃\n"
                "- 信息管控：作者控制信息投放节奏，每章一点新信息\n"
                "- 角色动机：所有行为背后必须有合理的心理动因\n"
                "- 时间线清晰：案件涉及的时间线必须经得起推敲"
            ),
            atmosphere=(
                "整体基调：紧张压抑 + 智力快感。"
                "调查场景需有细节的观察和推理氛围；"
                "对峙场景需有心理博弈的紧迫感；"
                "日常场景也要暗藏不安和违和感。"
            ),
            taboos=(
                "- 不要让侦探/主角通过超自然能力获得线索\n"
                "- 不要在最后一章才抛出关键证据（公平原则）\n"
                "- 不要让凶手/真相只是「因为他疯了」——需有深层动机\n"
                "- 不要过度依赖巧合推动剧情发展"
            ),
            tropes_to_use=(
                "- 红鲱鱼：精心设计的误导线索，让读者和侦探一起走弯路\n"
                "- 不可靠叙述：某个角色的叙述有选择性隐瞒\n"
                "- 密室/不在场证明：经典推理结构的创新运用\n"
                "- 多层真相：揭开一层真相后发现还有更深的秘密"
            ),
            tropes_to_avoid=(
                "- 开金手指：主角莫名其妙就猜到真相\n"
                "- 犯人独白：所有谜底靠犯人自己全说出来\n"
                "- 恐怖替代悬疑：用惊吓代替智力挑战\n"
                "- 无限巧合：所有线索都恰好出现在主角面前"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["案件", "案发", "现场", "尸体", "报案", "事件"],
                priority=90,
                beats=[
                    ("案发现场：现场细节描写、第一印象、初步线索", 600, "crime_scene"),
                    ("初步调查：证据收集、目击者询问、初步假设建立", 900, "investigation"),
                    ("疑点浮现：矛盾的证词、不合理的细节、新的方向", 700, "suspense"),
                    ("章末钩子：一个改变调查方向的新发现", 400, "suspense"),
                ],
            ),
            BeatTemplate(
                keywords=["调查", "线索", "追踪", "走访", "取证", "审讯"],
                priority=80,
                beats=[
                    ("调查准备：已有线索梳理、调查方向确定", 400, "sensory"),
                    ("深入调查：关键人物访谈、现场勘查、技术鉴定", 1000, "investigation"),
                    ("突破性线索：找到关键证据或发现重要矛盾", 800, "crime_scene"),
                    ("新的谜团：线索指向更复杂的真相", 500, "suspense"),
                ],
            ),
            BeatTemplate(
                keywords=["推理", "分析", "还原", "真相", "揭露", "破案"],
                priority=95,
                beats=[
                    ("线索汇总：所有已知信息的系统整理", 500, "investigation"),
                    ("推理过程：逐步排除、逻辑链构建、关键推断", 1000, "investigation"),
                    ("真相揭露：凶手/真相的揭示、证据链闭合", 900, "power_reveal"),
                    ("案后余波：各方反应、动机揭示、人性反思", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["对峙", "博弈", "试探", "心理战", "谈判"],
                priority=85,
                beats=[
                    ("对峙前：双方信息不对称分析、心理状态", 500, "sensory"),
                    ("心理博弈：言语试探、表情分析、信息攻防", 900, "investigation"),
                    ("关键交锋：一方露出破绽/被逼入绝境", 800, "power_reveal"),
                    ("博弈结果：新的力量对比、下一步行动", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["危险", "追逐", "陷阱", "威胁", "绑架", "逃脱"],
                priority=75,
                beats=[
                    ("危险降临：主角或关键人物陷入危险", 500, "sensory"),
                    ("生死时速：追逐/逃脱/对抗的紧张过程", 1000, "action"),
                    ("险中求索：在危险中发现新线索或真相碎片", 700, "crime_scene"),
                    ("脱险余波：事件的影响和新的威胁预兆", 400, "suspense"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "crime_scene": (
                "重点描写犯罪现场/关键场景：像一台高精度相机一样捕捉细节——"
                "物品的位置、痕迹的形态、气味和温度、不自然的地方。"
                "要引导读者和侦探一起观察，让读者有机会自己推理。"
                "关键线索要自然地混在普通细节中，不要刻意高亮。"
            ),
            "investigation": (
                "重点描写调查/推理过程：呈现完整的思维链——"
                "从观察到假设、从假设到验证、从排除到结论。"
                "让读者跟随侦探的思路，体验智力推理的快感。"
                "适当展示错误的推理方向，增加真实感。"
            ),
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：调查间隙】{outline}。"
            "主角在案件调查的间隙整理线索、补充调查，"
            "与搭档/线人交流，展现角色的日常一面。"
            "节奏稍缓但在角落里埋设新的疑点和不安。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：引人入胜的案件/异常事件，主角被质疑或被忽视", 400, "hook"),
                ("冲突爆发：其他人毫无头绪，案件陷入僵局", 500, "action"),
                ("★爽点爆发：主角展现超凡推理能力！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满！", 1400, "power_reveal"),
                ("悬念钩子：案件指向更深的秘密，远比表面复杂", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("深入现场：更细致的现场勘查", 600, "action"),
                ("★爽点延续：发现关键线索，小范围打脸质疑者", 1100, "power_reveal"),
                ("人物调查：询问嫌疑人/目击者", 600, "dialogue"),
                ("方向改变：新证据将调查引向意外方向", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：矛盾激化，真相比想象的更复杂", 400, "hook"),
                ("冲突展开：一个改变案件性质的重要发现", 700, "action"),
                ("★爽点爆发：第一次反转！初始假设被推翻！重点描写对手从得意到惊恐的表情变化", 1100, "power_reveal"),
                ("新的谜团：在解开一个谜团的同时，更大的谜团浮出水面", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        if any(kw in outline for kw in ["案件", "现场", "调查", "线索"]):
            required.append("调查场景需有细致的观察和逻辑推理")
            checks.append("检查推理是否有逻辑跳跃、线索是否凭空出现")

        if any(kw in outline for kw in ["真相", "揭露", "反转", "破案"]):
            required.append("真相揭露需有完整的证据链支撑")
            checks.append("检查关键证据是否在揭露前已出现过（公平原则）")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "悬疑题材张力评分修正：\n"
                "- 真相揭露/最终对峙/生死时刻 → 8-10\n"
                "- 关键线索发现/反转/心理博弈 → 6-8\n"
                "- 案件调查/走访取证/推理分析 → 5-7\n"
                "- 日常调查/信息整理 → 3-5\n"
                "- 角色日常/关系发展 → 2-4"
            ),
        )
