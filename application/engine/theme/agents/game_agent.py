"""游戏题材 Agent — 游戏世界/网游/电竞/系统流专项写作能力

核心能力：
- 游戏系统（等级、技能、装备、副本）的世界观约束
- 副本攻略/PVP对战/公会战/竞技比赛的专项节拍模板
- 游戏叙事节奏控制（操作展示、数据爽感、策略致胜）
- 缓冲章定制（日常练级、交易摆摊、公会管理）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class GameThemeAgent(ThemeAgent):
    """游戏题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "game"

    @property
    def genre_name(self) -> str:
        return "游戏"

    @property
    def description(self) -> str:
        return "游戏世界/网游/电竞/系统流题材，涵盖副本攻略、PVP对战、电竞比赛等核心元素"

    def get_system_persona(self) -> str:
        return (
            "你是一位深度游戏玩家兼网络小说大师，"
            "精通各类游戏机制（MMO、MOBA、FPS、开放世界）和电竞文化。"
            "你擅长将游戏系统的数据逻辑与文学叙事无缝融合，"
            "写出既有操作爽感又有剧情深度的游戏题材故事。"
            "你精通「操作碾压」「策略逆转」「以少胜多」等游戏爽文核心套路，"
            "让读者在阅读中体验到游戏中那种心跳加速的快感。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "游戏系统的数据（等级、属性、技能）要有一致的数值逻辑，不能随意膨胀",
            "操作描写要具体到按键/走位/技能释放时机，不能只写「操作很秀」",
            "装备/技能的描写要有游戏感（名称、品质、特效），但不能变成装备列表",
            "PVP/PVE场景中的胜负要有策略/操作依据，不能无理由翻盘",
            "游戏内的经济系统（金币、装备交易）要基本自洽",
            "区分游戏世界和现实世界的描写风格（游戏内更热血，现实更生活化）",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作世界观基于游戏设定：\n"
                "- 游戏系统（等级/技能/装备/副本）是核心框架\n"
                "- 数据和机制有明确规则，不能随意违反\n"
                "- 玩家之间存在竞争/合作的多层关系\n"
                "- 游戏公司/运营方的行为影响游戏生态\n"
                "- 游戏世界可能与现实有交互（如全息/脑机接口）"
            ),
            atmosphere=(
                "整体基调：热血竞技 + 操作爽感。"
                "战斗场景需有高速的节奏感和操作细节；"
                "副本场景需有团队配合的紧张感；"
                "竞技场景需有比赛的仪式感和观众反应。"
            ),
            taboos=(
                "- 不要让主角的操作描写变成「他随便按了几下就赢了」\n"
                "- 不要让游戏数值体系前后不一致\n"
                "- 不要让NPC的智能表现超出游戏设定的合理范围\n"
                "- 不要让装备/技能描写变成纯粹的数据列表"
            ),
            tropes_to_use=(
                "- 操作碾压：用极致操作战胜数据碾压的对手\n"
                "- 隐藏职业/技能：发现被其他人忽视的冷门流派并发扬光大\n"
                "- 公会争霸：大型团队对抗中的战术指挥和个人发挥\n"
                "- 竞技逆袭：在正式比赛中完成不可能的翻盘"
            ),
            tropes_to_avoid=(
                "- 数据碾压：主角等级/装备永远比所有人高\n"
                "- 系统偏爱：系统给主角独有的外挂式特权\n"
                "- 挂机升级：大段描写无聊的刷怪练级过程\n"
                "- 脱离游戏感：把游戏世界写成了纯粹的异世界"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["副本", "boss", "团本", "地牢", "raid", "通关"],
                priority=85,
                beats=[
                    ("副本信息：副本背景、boss机制预研、团队配置", 500, "sensory"),
                    ("攻略过程：小怪清理、机制触发、团队配合", 900, "game_action"),
                    ("Boss战：boss技能释放、走位判断、关键操作", 1000, "game_action"),
                    ("通关收获：装备掉落、成就达成、团队庆祝", 400, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["PVP", "对战", "竞技", "比赛", "擂台", "排位"],
                priority=90,
                beats=[
                    ("赛前分析：双方数据/战绩/流派分析", 500, "sensory"),
                    ("比赛开局：开局博弈、试探性交锋、节奏抢占", 800, "game_action"),
                    ("高潮对决：极限操作、关键技能释放、命悬一线", 1000, "game_action"),
                    ("赛后反响：数据回放、解说评论、对手反应", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["公会", "势力", "攻城", "工会战", "GVG", "据点"],
                priority=80,
                beats=[
                    ("战前部署：指挥部署、人员分配、战术制定", 600, "sensory"),
                    ("大规模战斗：多路并进、关键节点争夺、即时战术调整", 1100, "game_action"),
                    ("战局转折：奇兵突袭/关键操作/援军到达", 800, "power_reveal"),
                    ("战果统计：攻守结果、声望变化、势力版图更新", 400, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["装备", "打造", "强化", "锻造", "合成", "附魔"],
                priority=65,
                beats=[
                    ("材料收集：稀有材料的获取过程和来历", 400, "sensory"),
                    ("打造过程：制作步骤、数据变化、成功率悬念", 800, "game_action"),
                    ("成品展示：属性数据、特效描写、品质评定", 600, "power_reveal"),
                    ("实战检验：新装备的首次实战使用效果", 500, "game_action"),
                ],
            ),
            BeatTemplate(
                keywords=["探索", "隐藏", "彩蛋", "任务", "剧情", "NPC"],
                priority=70,
                beats=[
                    ("线索发现：发现隐藏内容/任务的契机", 500, "sensory"),
                    ("探索过程：解谜、触发条件、意外发现", 900, "game_action"),
                    ("重大发现：隐藏职业/技能/剧情的解锁", 700, "power_reveal"),
                    ("价值评估：发现的游戏价值和对主角的影响", 400, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "game_action": (
                "重点描写游戏操作过程：具体的技能名称和释放时机、"
                "走位的方向和距离感、操作的节奏和反应速度。"
                "要让读者感受到「手速」和「意识」的差别，"
                "如同在观看一场精彩的游戏直播。"
                "适当穿插数据变化（血量、蓝量、CD）但不要变成数据报告。"
            ),
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：日常游戏】{outline}。"
            "主角进行日常的练级/交易/社交活动，"
            "与公会成员互动，研究新的战术或流派。"
            "节奏轻松但暗中铺设下一个大型活动或对手的出现。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：精彩的对战/副本期，主角被质疑或轻视", 400, "hook"),
                ("冲突爆发：对手极限操作或数据碾压，主角看似不堪一击", 500, "action"),
                ("★爽点爆发：主角展露极限操作/隐藏职业/逆天数据！碾压或绝地翻盘！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满！", 1400, "power_reveal"),
                ("悬念钩子：暗示主角背后有特殊机缘/隐藏任务，更大的冒险在等待", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("实力展现：一场展现主角操作水平的战斗", 600, "action"),
                ("★爽点延续：极限操作小范围打脸质疑者", 1100, "power_reveal"),
                ("社交建立：加入公会/组队/结识队友", 600, "dialogue"),
                ("对手出现：引入主要竞争对手", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：与强劲对手的第一次正面交锋", 400, "hook"),
                ("冲突展开：让观众/读者热血沸腾的精彩对战", 700, "action"),
                ("★爽点爆发：名声初起！操作巅峰震撼全场！重点描写对手从得意到惊恐的表情变化", 1100, "power_reveal"),
                ("更大舞台：暗示更高级别的赛事/副本/挑战即将到来", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        if any(kw in outline for kw in ["PVP", "对战", "比赛", "竞技"]):
            required.append("对战场景需有具体的操作描写和策略分析")
            checks.append("检查对战是否只有结果没有过程")

        if any(kw in outline for kw in ["副本", "boss", "团本"]):
            required.append("副本场景需有boss机制和团队配合的描写")
            checks.append("检查boss战是否缺乏机制描写、变成纯数值碾压")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "游戏题材张力评分修正：\n"
                "- 总决赛/世界boss/终极副本 → 8-10\n"
                "- PVP对战/公会战/boss战 → 6-8\n"
                "- 副本攻略/排位赛/装备打造 → 5-7\n"
                "- 日常练级/交易/公会管理 → 3-5\n"
                "- 闲聊/逛街/研究攻略 → 2-4"
            ),
        )
