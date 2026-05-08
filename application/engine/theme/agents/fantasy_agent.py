"""奇幻题材 Agent — 西方奇幻/魔法世界专项写作能力

核心能力：
- 魔法体系与种族设定的世界观约束
- 史诗冒险/魔法对决/种族战争的专项节拍模板
- 奇幻叙事节奏控制（史诗感、命运叙事、善恶对抗）
- 缓冲章定制（旅途风光、酒馆休息、种族文化体验）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class FantasyThemeAgent(ThemeAgent):
    """奇幻题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "fantasy"

    @property
    def genre_name(self) -> str:
        return "奇幻"

    @property
    def description(self) -> str:
        return "西方奇幻/魔法世界题材，涵盖魔法体系、种族共存、史诗冒险等核心元素"

    def get_system_persona(self) -> str:
        return (
            "你是一位深谙西方奇幻叙事传统的小说大师，"
            "融合托尔金的史诗感、GRRM的人性深度与布兰登·桑德森的硬魔法逻辑。"
            "你擅长构建多种族共存的奇幻世界，"
            "写出既有史诗般宏大格局又有细腻人物刻画的奇幻故事。"
            "你精通「命运之子」「光暗对抗」「种族融合」等经典奇幻主题，"
            "让读者沉浸在一个充满魔法与传奇的异世界中。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "魔法体系必须有明确的规则和代价，不能让魔法成为万能的解决方案",
            "不同种族（精灵、矮人、兽人等）需有独特的文化、语言和行为逻辑",
            "战斗场景要结合魔法和武技，展现奇幻战斗的独特魅力",
            "世界地理和政治格局要自洽，王国/势力之间有合理的地缘关系",
            "预言/命运等元素不能成为唯一驱动力，角色需有自主选择",
            "神明/高等存在的行为需有其独立逻辑，不能只是给主角的工具",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作世界观基于西方奇幻体系：\n"
                "- 魔法有明确的来源（元素/神力/血脉等）和使用代价\n"
                "- 多种族共存，每个种族有独特的文明和能力\n"
                "- 神明/高等存在影响世界但不直接干预凡间\n"
                "- 王国/势力之间有复杂的政治和军事关系\n"
                "- 古老预言/遗迹/神器是推动剧情的重要线索"
            ),
            atmosphere=(
                "整体基调：史诗壮阔 + 冒险传奇。"
                "自然场景需有奇幻世界独有的瑰丽描写；"
                "战斗场景需有魔法与钢铁碰撞的壮观感；"
                "种族互动需体现文化差异和理解与尊重。"
            ),
            taboos=(
                "- 不要将所有非人种族写成「有尖耳朵/矮个子的人类」\n"
                "- 不要让魔法没有任何限制和代价\n"
                "- 不要让预言剥夺角色的自主选择\n"
                "- 不要让善恶二元对立过于简单化"
            ),
            tropes_to_use=(
                "- 命运之子：被预言选中的英雄踏上冒险之路\n"
                "- 种族联盟：不同种族放下成见共同面对威胁\n"
                "- 古老传承：上古时代的知识/力量被重新发现\n"
                "- 冒险团队：各有所长的队友共同成长"
            ),
            tropes_to_avoid=(
                "- 万能魔法：一个咒语解决所有问题\n"
                "- 种族歧视合理化：将某种族天生定义为邪恶\n"
                "- 旅途流水账：赶路过程写成无聊的日记\n"
                "- 龙傲天模式：主角在奇幻世界照样无敌碾压"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["魔法", "施法", "咒语", "法术", "元素", "魔力"],
                priority=80,
                beats=[
                    ("魔力汇聚：元素/魔力的聚集描写、施法准备", 500, "sensory"),
                    ("法术释放：咒语吟唱、魔法阵构建、元素操控", 1000, "magic_casting"),
                    ("魔法碰撞：法术对抗、魔力比拼、意外反馈", 800, "action"),
                    ("施法代价：魔力消耗、身体负担、环境影响", 400, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["冒险", "探索", "遗迹", "迷宫", "地牢", "任务"],
                priority=75,
                beats=[
                    ("冒险出发：目标确认、团队分工、装备准备", 500, "sensory"),
                    ("探索过程：陷阱/谜题/守卫、团队配合", 1000, "action"),
                    ("核心发现：宝物/真相/敌人出现", 800, "power_reveal"),
                    ("探险收获：经验/宝物获取、新线索揭示", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["战争", "攻城", "军团", "骑士", "进攻", "防守"],
                priority=85,
                beats=[
                    ("战前态势：双方军力对比、战术部署、盟友集结", 600, "sensory"),
                    ("战斗展开：骑兵冲锋/魔法轰击/攻城器械的壮观战场", 1100, "action"),
                    ("关键转折：英雄出击/援军抵达/魔法逆转", 800, "magic_casting"),
                    ("战后影响：伤亡统计、版图变化、新的同盟或仇恨", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["龙", "巨兽", "怪物", "猎杀", "巢穴"],
                priority=80,
                beats=[
                    ("怪物情报：目标生物的习性、弱点、危险等级", 500, "sensory"),
                    ("追踪接近：寻找巢穴、设置陷阱、接近目标", 800, "action"),
                    ("殊死搏斗：与强大生物的正面对决", 1000, "action"),
                    ("猎杀成果：战利品收获、声望提升、新的发现", 400, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["种族", "精灵", "矮人", "兽人", "外交", "联盟"],
                priority=70,
                beats=[
                    ("文化展示：异族领地的风土人情描写", 600, "sensory"),
                    ("交涉过程：文化碰撞、误解与理解、谈判角力", 900, "dialogue"),
                    ("关键突破：建立信任/达成协议/化解敌意", 700, "emotion"),
                    ("联盟成果：新的合作关系、共同目标确立", 400, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "magic_casting": (
                "重点描写魔法施展过程：魔力的流动感、元素的汇聚与操控、"
                "咒语/法阵的具体呈现、施法者的精神状态变化。"
                "要有奇幻魔法独有的华丽感和仪式感，"
                "同时体现魔法的规则和代价——力量从来不是免费的。"
            ),
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：旅途小憩】{outline}。"
            "冒险队伍在旅途中休整，探索异域风光，"
            "在酒馆/营火旁分享故事，加深队友间的情谊。"
            "节奏舒缓但暗中铺设下一场冒险或威胁的伏笔。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：奇幻世界的灾难场景（龙袭/魔法灾变/预言应验），主角被卷入危机却无人相助", 400, "hook"),
                ("冲突爆发：危机加剧，众人束手无策", 500, "action"),
                ("★爽点爆发：主角在灾难中展现超凡能力或触发命运之力！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满！", 1400, "power_reveal"),
                ("悬念钩子：暗示主角与预言/命运的特殊联系，留下短线悬念", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("冒险开启：事件将主角推上冒险之路", 600, "action"),
                ("★爽点延续：主角的魔法/战斗能力首次展现，小范围打脸质疑者", 1100, "power_reveal"),
                ("伙伴相遇：结识第一批冒险伙伴，性格互补的团队雏形", 600, "dialogue"),
                ("更大阴影：暗示笼罩世界的真正威胁", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：团队面对第一个真正的危险，对手轻视挑衅", 400, "hook"),
                ("冲突展开：协力作战的第一场战斗/挑战", 700, "action"),
                ("★爽点爆发：主角展现出超出预期的潜力！重点描写对手的惊恐和队友的震撼", 1100, "power_reveal"),
                ("命运暗示：发现主角的命运与更大的预言/使命相连", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        if any(kw in outline for kw in ["魔法", "施法", "法术", "咒语"]):
            required.append("魔法场景需有规则和代价的体现")
            checks.append("检查魔法是否成为无限制的万能工具")

        if any(kw in outline for kw in ["种族", "精灵", "矮人", "兽人"]):
            required.append("种族描写需有独特的文化和行为特征")
            checks.append("检查非人种族是否沦为「换了外表的人类」")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "奇幻题材张力评分修正：\n"
                "- 终极大战/世界存亡/命运对决 → 8-10\n"
                "- 军团战争/魔法对决/boss战 → 6-8\n"
                "- 冒险探索/怪物猎杀/遗迹探秘 → 5-7\n"
                "- 种族交流/城镇互动 → 3-5\n"
                "- 旅途风光/营火闲聊/购物补给 → 2-4"
            ),
        )
