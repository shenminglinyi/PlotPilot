"""仙侠题材 Agent — 修仙/仙侠/仙道专项写作能力

核心能力：
- 仙道体系（飞升、仙界、天道、因果）的世界观约束
- 区别于玄幻的更偏「道」与「悟」的修炼体系
- 仙侠特有的仙凡之别、天人交战、求道之心
- 缓冲章定制（参悟天道、云游四方、洞府修行）
"""

from typing import Dict, List, Optional
from application.engine.theme.theme_agent import (
    ThemeAgent,
    ThemeDirectives,
    ThemeAuditCriteria,
    BeatTemplate,
)


class XianxiaThemeAgent(ThemeAgent):
    """仙侠题材 Agent"""

    @property
    def genre_key(self) -> str:
        return "xianxia"

    @property
    def genre_name(self) -> str:
        return "仙侠"

    @property
    def description(self) -> str:
        return "仙侠/修仙/仙道题材，侧重求道之心、天人之辩、仙凡之别，比玄幻更注重意境与哲思"

    def get_system_persona(self) -> str:
        return (
            "你是一位深谙仙道哲学的仙侠小说大师，"
            "融合道家、佛家、儒家思想于笔端，以修仙问道为核心主题。"
            "你擅长以空灵悠远的意境为底色，"
            "写出既有仙凡之别的超越感，又有求道之心的执着与感动。"
            "你精通「以情入道」「天道无情」「逆天改命」等仙侠核心主题，"
            "让读者在瑰丽的仙侠世界中感受到对「道」的追求与思考。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "修仙境界的描写要侧重「悟道」过程——对天地法则的感悟，而非单纯的实力提升",
            "仙术/法术的描写要有意境美感（如「剑气化虹」而非「发射了一道能量波」）",
            "天劫/飞升等关键节点必须有庄严感和仪式感，不能草率带过",
            "仙凡之别的情感处理要细腻——百年修行看人间沧桑的感悟",
            "因果/气运/天道等概念需保持一致的设定逻辑",
            "仙侠世界的描写要有「画中仙境」的美感——云海、仙山、灵泉、瑞兽",
        ]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules=(
                "本作世界观基于仙侠修仙体系：\n"
                "- 修仙之路以「悟道」为核心，境界提升不只是实力增长\n"
                "- 天道规则（因果、劫数、气运）是最高层约束\n"
                "- 仙界/魔界/人间的三界结构层次分明\n"
                "- 寿元与境界挂钩，高境界者可活千年万年\n"
                "- 飞升渡劫是修仙者的终极目标，需要道心圆满"
            ),
            atmosphere=(
                "整体基调：空灵悠远 + 执着求道。"
                "仙境场景需有超凡脱俗的美感；"
                "战斗场景需有仙术法诀的华丽与意境；"
                "情感场景需有仙凡之间的深沉与感伤。"
            ),
            taboos=(
                "- 不要将仙侠写成换皮玄幻——区别在于「道」的追求和哲学思考\n"
                "- 不要让修仙变成纯粹的打怪升级\n"
                "- 不要忽视寿元差异对人际关系的影响\n"
                "- 不要让仙人表现得像凡人，需有超脱气质"
            ),
            tropes_to_use=(
                "- 逆天改命：不甘天道安排、以修仙之路对抗命运\n"
                "- 仙凡之恋：跨越寿元/境界的爱情带来的矛盾与感动\n"
                "- 道心坚固/崩塌：修道过程中的信念考验\n"
                "- 渡劫飞升：修仙者的终极考验和境界升华"
            ),
            tropes_to_avoid=(
                "- 纯爽文化：完全没有对「道」的思考，只有打斗升级\n"
                "- 仙界公务员：仙人的行为完全像现代官僚\n"
                "- 法宝堆砌：以法宝数量而非修为论高下\n"
                "- 境界注水：频繁突破但读者感受不到修为质变"
            ),
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(
                keywords=["悟道", "参悟", "天道", "感悟", "顿悟", "入定"],
                priority=85,
                beats=[
                    ("入定契机：触发感悟的事件/景象/对话", 400, "sensory"),
                    ("悟道过程：对天地法则的感知、道的本质的领悟", 1000, "dao_comprehension"),
                    ("境界蜕变：道心升华、法力质变、天地异象", 800, "power_reveal"),
                    ("悟后新境：以新的视角看世界、修为提升的具体体现", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["渡劫", "天劫", "飞升", "雷劫", "心魔"],
                priority=95,
                beats=[
                    ("劫前准备：选择渡劫之地、布置阵法、交代后事", 500, "sensory"),
                    ("天劫降临：劫云汇聚、天地变色、雷劫/心魔的具体呈现", 1000, "action"),
                    ("生死之间：肉身崩溃与重塑、道心动摇与坚守", 900, "dao_comprehension"),
                    ("劫后重生：渡劫成功/失败、境界蜕变、天地感应", 500, "power_reveal"),
                ],
            ),
            BeatTemplate(
                keywords=["斗法", "法诀", "仙术", "对决", "法宝"],
                priority=80,
                beats=[
                    ("斗法前奏：双方气机锁定、法力外放、天地灵气汇聚", 500, "sensory"),
                    ("仙术对抗：法诀施展、法宝对碰、术法意境的碰撞", 1000, "martial_arts"),
                    ("道的较量：不只是力量比拼，更是对「道」理解的交锋", 800, "dao_comprehension"),
                    ("胜负之后：修为感悟、道心变化、因果结算", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["仙凡", "尘缘", "情劫", "离别", "轮回", "转世"],
                priority=75,
                beats=[
                    ("情境铺垫：仙凡之间的羁绊和矛盾", 500, "emotion"),
                    ("情感深入：超越寿元/境界的情感互动", 900, "dialogue"),
                    ("抉择时刻：情与道的冲突、舍与得的考验", 800, "dao_comprehension"),
                    ("结局处理：离别/圆满/化解，情感的升华", 500, "emotion"),
                ],
            ),
            BeatTemplate(
                keywords=["洞府", "仙山", "秘境", "灵脉", "仙府", "传承"],
                priority=70,
                beats=[
                    ("仙境描写：超凡脱俗的自然美景和灵气氛围", 600, "sensory"),
                    ("探索/修行：在仙境中的具体活动和收获", 900, "dao_comprehension"),
                    ("机缘/传承：仙人遗留的道统/法宝/功法", 700, "power_reveal"),
                    ("离境感悟：带着收获离开，对修仙之路有更深理解", 400, "emotion"),
                ],
            ),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "dao_comprehension": (
                "重点描写悟道/修行过程：对天地法则的感知不是数据罗列，"
                "而是以诗意的、哲学的方式呈现修仙者与天道的对话。"
                "可以借鉴道家「天人合一」、佛家「明心见性」的意境，"
                "让读者在阅读中也能感受到一种精神上的升华。"
                "避免将悟道写成「获得了一个技能」的游戏式表述。"
            ),
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return (
            f"【缓冲章：云游悟道】{outline}。"
            "主角在仙山福地或凡间游历，参悟大道至理，"
            "以超脱视角审视人间百态，感悟修仙与做人的关系。"
            "节奏空灵舒缓，暗中铺设下一次劫数或机缘的伏笔。"
        )

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇拉仇恨：与仙/道相关的异变事件（仙人渡劫异象/灵气异动/天道异变），主角被轻视为凡人", 400, "hook"),
                ("冲突爆发：异变加剧，众修士束手无策", 500, "action"),
                ("★爽点爆发：主角在异变中展现修仙天赋或获得仙缘！重点描写反派的不可置信和旁观者的极度震惊。短促句子，情绪拉满！", 1400, "power_reveal"),
                ("悬念钩子：暗示主角与天道的特殊联系，更大的仙路冒险即将展开", 400, "suspense"),
            ]
        elif chapter_number == 2:
            return [
                ("修行入门：主角开始正式修行", 600, "action"),
                ("★爽点延续：初次悟道或感知灵气时展露天赋，小范围打脸质疑者", 1100, "power_reveal"),
                ("仙路人脉：结识同修/师长/道友", 600, "dialogue"),
                ("天道暗示：暗示主角身上背负的因果/使命", 400, "suspense"),
            ]
        elif chapter_number == 3:
            return [
                ("挑衅升级：第一次真正的修仙考验迫近", 400, "hook"),
                ("冲突展开：心魔/战斗/抉择的考验过程", 700, "action"),
                ("★爽点爆发：初露锋芒！展现与众不同的修行天赋！重点描写对手从得意到惊恐的表情变化", 1100, "power_reveal"),
                ("仙路漫漫：通过此次考验窥见修仙之路的艰辛与壮阔", 400, "suspense"),
            ]
        return None

    def get_audit_criteria(
        self,
        chapter_number: int,
        outline: str,
    ) -> ThemeAuditCriteria:
        required = []
        checks = []

        if any(kw in outline for kw in ["悟道", "修行", "参悟", "突破"]):
            required.append("修行场景需有对'道'的哲学思考，而非纯粹的数值提升")
            checks.append("检查修行描写是否沦为游戏式的升级表述")

        if any(kw in outline for kw in ["斗法", "对决", "法术", "仙术"]):
            required.append("斗法场景需有仙术意境描写，不能写成武侠打斗")
            checks.append("检查仙术描写是否有空灵的意境美感")

        return ThemeAuditCriteria(
            required_elements=required,
            quality_checks=checks,
            tension_guidance=(
                "仙侠题材张力评分修正：\n"
                "- 渡劫/飞升/仙魔大战 → 8-10\n"
                "- 斗法对决/道心考验 → 6-8\n"
                "- 悟道修行/仙府探秘 → 5-7\n"
                "- 云游四方/仙凡交流 → 3-5\n"
                "- 洞府修行/采药炼丹 → 2-4"
            ),
        )
