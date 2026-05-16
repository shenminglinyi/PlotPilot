"""通用/其他题材 Agent — 不属于特定分类时的通用写作增强

核心能力：
- 通用的叙事结构和节奏控制增强
- 适用于多种混合题材或难以归类的独特题材
- 提供基础的节拍模板和写作规则加强
- 缓冲章定制（日常过渡、人物塑造、伏笔铺设）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class OtherThemeAgent(ThemeAgent):
    """通用/其他题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "other"

    @property
    def genre_name(self) -> str:
        return "其他"

    @property
    def description(self) -> str:
        return "通用题材增强，适用于混合题材或不属于特定分类的创新题材"

    def get_system_persona(self) -> str:
        return (
            "你是一位博览群书、风格多变的网络小说大师，"
            "不拘泥于单一题材，善于融合多种叙事元素。"
            "你擅长发现每个故事独特的叙事节奏和表达方式，"
            "写出既有类型小说的可读性又有文学性追求的故事。"
            "你精通各种叙事技巧，能够根据故事需要灵活调整写作策略。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "每个场景都要有明确的功能——推动剧情、塑造人物或营造氛围，不写无意义的过场",
            "对话要推动剧情或展现人物，避免纯粹的信息灌输式对话",
            "场景转换要有合理的时间和空间逻辑，不能无预告地跳转",
            "伏笔的埋设和回收要有节奏感——太密集显刻意，太稀疏读者会忘记",
            "保持叙事视角的一致性，不要在同一场景中随意切换视角",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作需保持基本的叙事逻辑：\n"
                "- 世界观设定需在早期章节自然展现，避免后期突然改变规则\n"
                "- 角色行为需与其性格/背景一致\n"
                "- 力量/能力体系如有，需保持前后一致\n"
                "- 时间线需清晰可追溯"
            ),
            atmosphere=(
                "根据当前章节的内容自然调整基调。"
                "行动场景需有节奏感；"
                "情感场景需有细腻的心理描写；"
                "日常场景需有生活的质感和趣味。"
            ),
            taboos=(
                "- 不要让角色行为脱离其性格设定\n"
                "- 不要用旁白直接告诉读者应该怎么感受\n"
                "- 不要让所有角色的说话方式都一样\n"
                "- 不要在没有任何铺垫的情况下出现重大转折"
            ),
            tropes_to_use=(
                "- 草蛇灰线：早期的细节在后期产生重要影响\n"
                "- 人物成长弧：角色通过经历发生可信的变化\n"
                "- 多线并行：多条叙事线最终交汇产生化学反应\n"
                "- 场景即人物：通过环境描写折射人物心理"
            ),
            tropes_to_avoid=(
                "- 降智推剧情：让角色变笨来制造冲突\n"
                "- 机械降神：无铺垫地引入外部力量解决问题\n"
                "- 同质化：所有角色的反应和说话方式都一样\n"
                "- 水文凑字数：大段无意义的描写或重复"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["冲突", "对抗", "战斗", "对决", "危机"],
                priority=80,
                beats=[
                    ("冲突前奏：矛盾积累到临界点、各方立场明确", 500, "sensory"),
                    ("冲突展开：正面对抗/博弈/交锋的具体过程", 1000, "action"),
                    ("高潮转折：关键变数出现、局势逆转", 800, "power_reveal"),
                    ("冲突余波：结果和影响、新的格局", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["揭秘", "真相", "发现", "秘密", "揭露"],
                priority=85,
                beats=[
                    ("悬念铺垫：异常/疑点的积累", 500, "suspense"),
                    ("调查追踪：接近真相的过程", 900, "action"),
                    ("真相揭露：谜底揭开的震撼时刻", 800, "power_reveal"),
                    ("反应余波：真相带来的影响和新局面", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["成长", "蜕变", "考验", "突破", "领悟"],
                priority=75,
                beats=[
                    ("困境呈现：角色面临的挑战或困境", 500, "sensory"),
                    ("挣扎过程：尝试、失败、反思的过程", 900, "emotion"),
                    ("突破时刻：关键的领悟或能力突破", 800, "power_reveal"),
                    ("成长确认：变化后的角色展现新的面貌", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["告别", "离别", "重逢", "回归", "旅程"],
                priority=70,
                beats=[
                    ("情感铺垫：即将分离/重逢的氛围营造", 500, "sensory"),
                    ("关键场景：告别/重逢的具体场景和对话", 900, "dialogue"),
                    ("情感爆发：压抑情感的释放", 700, "emotion"),
                    ("新的开始：告别后的新方向或重逢后的新生活", 400, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {}

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：日常过渡】{outline}。"
            "角色在紧张事件后的休整，展现日常生活的细节和人物关系。"
            "节奏舒缓但通过对话或细节暗中推进暗线，为下一个高潮蓄力。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：一个有冲击力的事件/场景，主角被质疑或被忽视", 400, "hook"),
                ("冲突爆发：矛盾激化，对方嚣张得意", 500, "action"),
                ("★爽点爆发：主角展露隐藏能力/身份！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满，切忌平铺直叙！", 1400, "power_reveal"),
                ("悬念钩子：暗示主角的特殊之处远不止此，留下短线悬念", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("承接拓展：在首章基础上拓展世界观和人物关系", 600, "action"),
                ("★爽点延续：更深入地展示主角的能力或独特之处，小范围打脸质疑者", 1100, "power_reveal"),
                ("关系建立：引入关键配角，建立核心人物关系", 600, "dialogue"),
                ("更大图景：暗示更广阔的世界和更大的冲突", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：主角面临第一个真正的挑战", 400, "hook"),
                ("冲突展开：一场精彩的对抗/考验/冒险", 700, "action"),
                ("★爽点爆发：证明自己！展现出超出预期的能力/品质！重点描写对手从嚣张到惊恐的表情变化", 1100, "power_reveal"),
                ("新篇开启：通过此事打开新的故事空间", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        return ThemeAuditCriteria(
            required_elements=[],
            quality_checks=[
                "检查场景描写是否有生动的感官细节",
                "检查对话是否推动了剧情或展现了人物",
            ],
            tension_guidance=(
                "通用张力评分修正：\n"
                "- 生死攸关/终极对决/情感高潮 → 8-10\n"
                "- 关键冲突/重大发现/重要对抗 → 6-8\n"
                "- 中等冲突/成长考验/关系变化 → 5-7\n"
                "- 日常生活/关系维护/信息铺垫 → 3-5\n"
                "- 纯过渡/休憩/旅途 → 2-4"
            ),
        )
