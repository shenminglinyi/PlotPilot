"""科幻题材 Agent — 硬科幻/软科幻/赛博朋克专项写作能力

核心能力：
- 科学理论与技术设定的世界观约束
- 太空探索/AI觉醒/时间悖论/赛博朋克的专项节拍模板
- 科幻叙事节奏控制（概念震撼、技术悬念、文明碰撞）
- 缓冲章定制（科研日常、太空航行、技术研讨）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class ScifiThemeAgent(ThemeAgent):
    """科幻题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "scifi"

    @property
    def genre_name(self) -> str:
        return "科幻"

    @property
    def description(self) -> str:
        return "硬科幻/软科幻/赛博朋克题材，涵盖太空探索、AI觉醒、未来社会等核心元素"

    # ─── 1. 人设 ───

    def get_system_persona(self) -> str:
        return (
            "你是一位兼具科学素养和文学功底的科幻小说大师，"
            "熟悉物理学、天文学、计算机科学、生物工程等前沿领域。"
            "你擅长将深奥的科学概念转化为引人入胜的故事情节，"
            "在「硬核设定」和「可读性」之间找到完美平衡。"
            "你精通「概念震撼」「技术悬念」「文明尺度叙事」等科幻写作技巧，"
            "让读者既能享受故事，又能感受到科学之美和宇宙之大。"
        )

    # ─── 2. 写作规则 ───

    def get_writing_rules(self) -> List[str]:
        return [
            "涉及的科学原理必须有基本依据，可以合理外推但不能违反已知物理定律（除非设定中明确说明）",
            "技术描写要具体而非模糊（不要写「用了某种高科技手段」，要有具体的技术细节）",
            "外星文明/AI 的行为逻辑必须自洽，不能用人类思维模式套用非人类存在",
            "太空场景要体现真实的宇宙环境特点（真空、辐射、距离、时间延迟等）",
            "科技发展的社会影响必须合理推演，技术改变要引发相应的社会结构变化",
            "避免用魔法式的「科技」解决问题（如「纳米机器人能做一切」）",
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
                "本作世界观基于科幻设定：\n"
                "- 科技水平有明确的层级和限制，不能随意突破\n"
                "- 物理定律是基础约束（可有合理的科幻外推）\n"
                "- 社会结构要与技术水平相匹配\n"
                "- 信息传播和交通方式决定文明形态\n"
                "- 资源和能源是文明发展的核心驱动力"
            ),
            atmosphere=(
                "整体基调：理性探索 + 概念震撼。"
                "太空场景需有宏大的宇宙尺度感；"
                "技术场景需有精密的机械/数字美学；"
                "人文场景需有技术变革下的人性思考。"
            ),
            taboos=(
                "- 不要出现无法自圆其说的超光速/时间旅行（需有理论框架支撑）\n"
                "- 不要让科技成为「万能魔法」——任何技术都有代价和限制\n"
                "- 不要忽视太空环境的真实危险（辐射、真空、微重力影响等）\n"
                "- 不要让外星文明表现得像戴面具的人类"
            ),
            tropes_to_use=(
                "- 概念震撼：用一个科学概念的推演让读者感受到认知升级\n"
                "- 技术悬念：技术故障/限制制造的紧张感\n"
                "- 文明碰撞：不同技术路线/文明形态的接触与冲突\n"
                "- 尺度跳跃：从个人视角突然拉开到宇宙/文明尺度"
            ),
            tropes_to_avoid=(
                "- 人形外星人：外星文明只是「长得不一样的人类」\n"
                "- 科技万能：技术没有任何副作用或社会影响\n"
                "- 太空歌剧化：完全忽视物理现实的太空战斗\n"
                "- 终极武器：一个超级发明解决所有问题"
            ),
        )

    # ─── 4. 节拍模板 ───

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["探索", "星球", "太空", "航行", "殖民", "外星"],
                priority=80,
                beats=[
                    ("环境描写：太空/星球的宏大场景、物理环境的真实细节", 600, "sensory"),
                    ("探索过程：发现异常、数据分析、假设验证、危险应对", 1000, "discovery"),
                    ("核心发现：改变认知的重大发现、概念震撼时刻", 800, "power_reveal"),
                    ("影响评估：发现的意义、对任务/文明的影响、新的问题", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["AI", "意识", "觉醒", "虚拟", "数字", "模拟"],
                priority=85,
                beats=[
                    ("异常信号：AI行为异常/意识萌芽的细微迹象", 500, "suspense"),
                    ("深入调查：图灵测试/意识验证、伦理困境浮现", 900, "discovery"),
                    ("关键对话：人机之间深层次的哲学对话、认知碰撞", 800, "dialogue"),
                    ("抉择时刻：关于AI权利/威胁的重大决定、各方立场", 600, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["战争", "战斗", "军事", "舰队", "防御", "入侵"],
                priority=75,
                beats=[
                    ("战前态势：双方技术实力对比、战术部署、信息战", 600, "sensory"),
                    ("战斗展开：武器系统运作、太空战术机动、技术对抗", 1000, "action"),
                    ("技术逆转：利用科学原理/技术创新改变战局", 800, "discovery"),
                    ("战后影响：伤亡评估、技术代差反思、新的威胁", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["实验", "研究", "发明", "突破", "理论", "验证"],
                priority=70,
                beats=[
                    ("问题定义：科学难题的背景、已有的研究进展", 500, "sensory"),
                    ("实验过程：具体的实验设计、数据收集、意外发现", 900, "discovery"),
                    ("突破时刻：关键数据出现、理论验证/颠覆", 700, "power_reveal"),
                    ("意义延伸：发现的应用前景、潜在危险、伦理思考", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["末日", "灾难", "生存", "避难", "资源", "荒废"],
                priority=75,
                beats=[
                    ("灾难呈现：末日场景的具体描写、生存环境的严酷", 600, "sensory"),
                    ("生存挣扎：资源获取、危险应对、人性考验", 1000, "action"),
                    ("关键抉择：生存与道德的冲突、群体与个人的取舍", 700, "emotion"),
                    ("希望/绝望：新发现带来转机或更大的危机", 500, "suspense"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "discovery": (
                "重点描写科学发现过程：数据异常的捕捉、假设的建立与验证、"
                "实验的具体操作、发现真相时的认知震撼。"
                "要让读者跟随角色一起经历发现的过程，感受到智力的快感。"
                "避免「突然发现了」式的跳跃，要有完整的推理链。"
            ),
        }

    # ─── 5. 缓冲章模板 ───

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：科研日常】{outline}。"
            "角色进行常规科研工作或太空航行日常，"
            "展现科技生活的细节和人物之间的关系。"
            "节奏舒缓但暗中埋设下一个技术危机或发现的种子。"
        )

    # ─── 6. 开篇定制 ───

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：震撼的科幻场景（太空异象/技术事故/异常信号），主角被质疑或排挤", 400, "hook"),
                ("冲突爆发：危机加剧，其他人束手无策", 500, "action"),
                ("★爽点爆发：主角展现天才级的科学洞察/操作能力！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满！", 1400, "power_reveal"),
                ("悬念钩子：暗示异常背后有更宏大的真相/文明级别的危机", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("深入调查：主角开始追查异常", 600, "action"),
                ("★爽点延续：通过具体操作/实验展现能力，小范围打脸质疑者", 1100, "power_reveal"),
                ("人物关系：引入关键配角，建立团队", 600, "dialogue"),
                ("更大图景：暗示异常背后有更宏大的原因", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：异常事件扩大或出现第二个关联事件", 400, "hook"),
                ("冲突展开：用科学手段应对第一个真正的危机", 700, "action"),
                ("★爽点爆发：认知突破！发现改变理解的关键信息！重点描写对手从得意到惊恐的表情变化", 1100, "power_reveal"),
                ("新维度展开：意识到问题的规模远超预期", 400, "suspense"),
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

        if any(kw in outline for kw in ["太空", "星球", "飞船", "航行"]):
            required.append("太空场景需体现真实的物理环境特点")
            checks.append("检查是否忽视了真空/辐射/距离等太空环境要素")

        if any(kw in outline for kw in ["实验", "研究", "发现", "理论"]):
            required.append("科研场景需有具体的实验/推理过程")
            checks.append("检查科学发现是否过于突兀、缺乏推理过程")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "科幻题材张力评分修正：\n"
                "- 文明级别危机/终极对抗 → 8-10\n"
                "- 太空战斗/技术对抗 → 6-8\n"
                "- 重大科学发现/认知颠覆 → 5-7\n"
                "- 科研日常/航行生活 → 3-5\n"
                "- 人物对话/哲学思辨 → 2-4"
            ),
        )
