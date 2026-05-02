"""CoC 初始模板服务。"""
from __future__ import annotations

from typing import Any


class CocPresetService:
    """将预设模板批量写入 CoC 正典/线索/道具账本。"""

    def __init__(self, canon_service, clue_service, prop_ledger_service=None):
        self.canon_service = canon_service
        self.clue_service = clue_service
        self.prop_ledger_service = prop_ledger_service

    def list_presets(self) -> list[dict[str, Any]]:
        presets = []
        for preset in self._preset_definitions():
            presets.append({
                "key": preset["key"],
                "name": preset["name"],
                "description": preset["description"],
                "source_novel_id": preset["source_novel_id"],
                "canon_count": len(preset["canon_entries"]),
                "clue_count": len(preset["clue_items"]),
                "prop_count": len(preset.get("prop_items") or []),
            })
        return presets

    def apply_preset(
        self,
        *,
        novel_id: str,
        preset_key: str = "analysis-loop-721",
        overwrite_existing: bool = False,
    ) -> dict[str, Any]:
        preset = self._get_preset((preset_key or "").strip().lower())
        if preset is None:
            raise ValueError(f"unknown preset_key: {preset_key}")

        created_canon = 0
        created_clues = 0
        created_props = 0
        skipped = 0

        for item in preset["canon_entries"]:
            existing = self.canon_service.repository.get_entry_by_key(
                novel_id,
                item["canon_type"],
                item["title"],
            )
            if existing and not overwrite_existing:
                skipped += 1
                continue
            self.canon_service.upsert_entry(novel_id=novel_id, **item)
            created_canon += 1

        for item in preset["clue_items"]:
            existing = self.clue_service.repository.get_item_by_key(novel_id, item["clue_key"])
            if existing and not overwrite_existing:
                skipped += 1
                continue
            self.clue_service.upsert_item(novel_id=novel_id, **item)
            created_clues += 1

        if self.prop_ledger_service is not None:
            for item in preset.get("prop_items") or []:
                existing = self.prop_ledger_service.repository.get_item_by_name(novel_id, item["name"])
                if existing and not overwrite_existing:
                    skipped += 1
                    continue
                self.prop_ledger_service.upsert_item(novel_id=novel_id, **item)
                created_props += 1

        return {
            "preset_key": preset["key"],
            "novel_id": novel_id,
            "created_canon": created_canon,
            "created_clues": created_clues,
            "created_props": created_props,
            "skipped": skipped,
            "overwrite_existing": bool(overwrite_existing),
        }

    @classmethod
    def _get_preset(cls, key: str) -> dict[str, Any] | None:
        return next((item for item in cls._preset_definitions() if item["key"] == key), None)

    @classmethod
    def _preset_definitions(cls) -> list[dict[str, Any]]:
        return [
            cls._analysis_loop_721_preset(),
            cls._fog_harbor_gray_card_preset(),
        ]

    @staticmethod
    def _analysis_loop_721_preset() -> dict[str, Any]:
        return {
            "key": "analysis-loop-721",
            "name": "循环隧道·721（分析模板）",
            "description": "基于已分析的循环悬疑样本抽取：固定叙事边界、核心规则、延迟揭示线索。",
            "source_novel_id": "novel-1777374690524",
            "canon_entries": [
                {
                    "canon_type": "world_rule",
                    "title": "叙事视角边界",
                    "public_facts": "全书坚持第三人称限制视角，信息边界以主角当前感知为准。",
                    "hidden_truth": "",
                    "lock_level": "absolute",
                    "mutable_notes": "可加强体感细节，但不能切换全知叙述。",
                    "status": "active",
                },
                {
                    "canon_type": "timeline",
                    "title": "第七次熄灯与十七分钟窗口",
                    "public_facts": "第七次熄灯后，关键窗口为十七分钟，剧情推进围绕窗口前后触发。",
                    "hidden_truth": "窗口触发与更高层循环校准有关。",
                    "lock_level": "strict",
                    "mutable_notes": "窗口长度不可随意改写；若变更需先登记正典事件。",
                    "status": "active",
                },
                {
                    "canon_type": "artifact",
                    "title": "721 座椅数字机制",
                    "public_facts": "721 不是装饰编号，具备实际触发/位移意义。",
                    "hidden_truth": "721 与主控逻辑的倒序频率耦合，能牵引时间层切换。",
                    "lock_level": "absolute",
                    "mutable_notes": "不得写成普通噪音或随机巧合。",
                    "status": "active",
                },
                {
                    "canon_type": "world_rule",
                    "title": "B-721-M 维护口定位",
                    "public_facts": "B-721-M 是系统内部维护入口，关联关键人物失踪与回传信息。",
                    "hidden_truth": "入口同时承担观测与重写权限争夺。",
                    "lock_level": "strict",
                    "mutable_notes": "可补充细节，但入口性质不改。",
                    "status": "active",
                },
                {
                    "canon_type": "character_truth",
                    "title": "周牧野立场双重性",
                    "public_facts": "周牧野既提供线索也制造阻力，行为呈校准者特征。",
                    "hidden_truth": "其行动受高层循环指令约束，存在镜像身份来源。",
                    "lock_level": "strict",
                    "mutable_notes": "阶段内可保持暧昧，不可突兀洗白或突兀脸谱化。",
                    "status": "active",
                },
                {
                    "canon_type": "character_truth",
                    "title": "苏晓跨时信息链",
                    "public_facts": "苏晓通过跨时信号持续留下碎片信息，指向更深层规则。",
                    "hidden_truth": "其状态与主角记忆结构绑定，非普通失踪。",
                    "lock_level": "strict",
                    "mutable_notes": "公开层可渐进推进，真相层仅按节奏揭露。",
                    "status": "active",
                },
            ],
            "clue_items": [
                {
                    "clue_key": "clue-721-morse",
                    "clue_text": "721 数字以摩斯式节律反复出现，不是普通故障。",
                    "visibility": "reader_known",
                    "reveal_chapter": 1,
                    "known_by": "主角",
                    "confidence": 0.88,
                    "lock_level": "strict",
                    "status": "active",
                    "notes": "用于多章回收的基础线索。",
                },
                {
                    "clue_key": "clue-b721m-entry",
                    "clue_text": "B-721-M 维护口与关键失踪事件相关，入口可被特定条件触发。",
                    "visibility": "protagonist_known",
                    "reveal_chapter": 2,
                    "known_by": "主角,陈维",
                    "confidence": 0.82,
                    "lock_level": "strict",
                    "status": "active",
                    "notes": "保持入口性质稳定。",
                },
                {
                    "clue_key": "clue-17min-window",
                    "clue_text": "十七分钟是关键反应窗口，超时后规则会发生偏移。",
                    "visibility": "reader_known",
                    "reveal_chapter": 3,
                    "known_by": "主角,周牧野",
                    "confidence": 0.74,
                    "lock_level": "soft",
                    "status": "active",
                    "notes": "常用于段落倒计时。",
                },
                {
                    "clue_key": "clue-double-manual",
                    "clue_text": "1970 与 2023 的双手册存在互证与冲突信息。",
                    "visibility": "protagonist_known",
                    "reveal_chapter": 3,
                    "known_by": "主角,周牧野",
                    "confidence": 0.77,
                    "lock_level": "soft",
                    "status": "active",
                    "notes": "适合做误导与校正。",
                },
                {
                    "clue_key": "clue-zhou-origin",
                    "clue_text": "周牧野可能并非单一时间线个体，来源与循环层有关。",
                    "visibility": "author_only",
                    "reveal_chapter": None,
                    "known_by": "作者",
                    "confidence": 0.71,
                    "lock_level": "absolute",
                    "status": "active",
                    "notes": "作者层线索，严禁正文直出。",
                },
                {
                    "clue_key": "clue-suxiao-binding",
                    "clue_text": "苏晓状态与主角记忆结构耦合，非普通生死状态。",
                    "visibility": "author_only",
                    "reveal_chapter": None,
                    "known_by": "作者",
                    "confidence": 0.7,
                    "lock_level": "absolute",
                    "status": "active",
                    "notes": "作者层线索，需拆分为多次渐进揭露。",
                },
            ],
            "prop_items": [],
        }

    @staticmethod
    def _fog_harbor_gray_card_preset() -> dict[str, Any]:
        return {
            "key": "fog-harbor-gray-card",
            "name": "雾港灰卡调查团",
            "description": "原创 CoC 风格任务流模板：白雨翔、第七档案局、灰卡副本、认知污染与第一季主线。",
            "source_novel_id": "原创模板",
            "canon_entries": _FOG_HARBOR_CANON_ENTRIES,
            "clue_items": _FOG_HARBOR_CLUE_ITEMS,
            "prop_items": _FOG_HARBOR_PROP_ITEMS,
        }


_FOG_HARBOR_CANON_ENTRIES: list[dict[str, Any]] = [
    {
        "canon_type": "world_rule",
        "title": "系列模式：雾港灰卡调查团",
        "public_facts": "本书采用任务流、多异常世界调查、固定主角团结构。白雨翔和第七档案局小组会被灰卡派往不同异常现场，每个副本独立成案，同时回收同一条主线。",
        "hidden_truth": "所有任务都在筛选和训练见证人。主角团以为自己在救援和封缄，实际正在补齐一个旧仪式需要的观察、记录、证明和代价。",
        "lock_level": "absolute",
        "mutable_notes": "可以更换副本外壳，但不能改成普通冒险、纯打怪或无限升级流。",
        "status": "active",
    },
    {
        "canon_type": "character_truth",
        "title": "主角：白雨翔",
        "public_facts": "白雨翔是雾港第七档案局记录员，曾做调查记者，擅长从证词、旧报纸、照片边角和档案删改处发现矛盾。他的职责是记录任务经过，并决定哪些内容进入正式档案。",
        "hidden_truth": "白雨翔并不是第一次接触灰卡。他曾经参与过一次失败见证，相关记忆被档案局封存，而灰卡持续选择他，是因为他能把异常转写成可被现实承认的记录。",
        "lock_level": "absolute",
        "mutable_notes": "可调整过往细节，但不能改掉记录员/前记者/被灰卡反复选中的核心定位。",
        "status": "active",
    },
    {
        "canon_type": "artifact",
        "title": "灰卡任务机制",
        "public_facts": "灰卡会在无人注视时出现任务文字，通常只给地点、时限和一个看似可救的人。任务文字会随调查进展发生小幅变化，但不会主动解释真相。",
        "hidden_truth": "灰卡不是通讯工具，而是旧仪式的分发器。它通过任务把调查员送入不同异常叙事，让他们完成见证、命名、封缄或献祭中的某一环。",
        "lock_level": "absolute",
        "mutable_notes": "灰卡可以误导，但不能像系统面板一样直接发布奖励、等级或完整解释。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "雾港第七档案局",
        "public_facts": "第七档案局是雾港地下异常档案机构，对外不存在正式编制。它处理无法归入刑事、民事和自然灾害档案的事件，成员以档案员、顾问、外勤和证物管理员为主。",
        "hidden_truth": "档案局并非完全站在人类一侧。局内高层知道灰卡会筛选见证人，却长期把任务包装成应急救援，以换取雾港多年表面平静。",
        "lock_level": "strict",
        "mutable_notes": "可增设部门和人物，但档案局的暧昧立场要保留。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "异常世界进入与退出",
        "public_facts": "每个副本都有入口、时限和退出条件。入口形态由当次大纲决定；退出条件通常不是杀死怪物，而是确认真相、完成封缄或带走指定证据。",
        "hidden_truth": "副本不是完整世界，而是被旧仪式切出的异常叙事片段。调查员在片段中做出的记录会反向改变现实档案。",
        "lock_level": "absolute",
        "mutable_notes": "副本规则可变化，但必须有清晰入口、时限、代价和退出条件。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "认知污染与理智代价",
        "public_facts": "越接近异常真相，调查员越容易出现记忆断片、感官错位、熟人陌生化、时间感错误和身份边界松动。代价首先表现为认知偏移，而不是数值扣减。",
        "hidden_truth": "所谓理智损耗不是精神脆弱，而是人类认知被迫容纳非人结构。每次成功封缄都会留下一个小缺口，最终让白雨翔能看见完整仪式。",
        "lock_level": "absolute",
        "mutable_notes": "不得写成简单发疯或游戏数值；代价要具体落在记忆、关系、判断和身体感上。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "异常源不可真正杀死",
        "public_facts": "主角团能阻止扩散、救出部分人、封住入口或拿走关键证据，但无法真正杀死异常源。每个胜利都必须带着未解决的残留。",
        "hidden_truth": "异常源只是旧仪式的投影。不同副本的具体表现需要随连载大纲逐步登记，不能在初始模板里全部写死。",
        "lock_level": "strict",
        "mutable_notes": "结局可以阶段性胜利，但不能把副本写成彻底通关。",
        "status": "active",
    },
    {
        "canon_type": "character_truth",
        "title": "固定主角团功能位",
        "public_facts": "核心小组由白雨翔、许照、周闻笙、陈泊舟组成。白雨翔负责记录和叙事漏洞；许照负责尸检、现场和证据链；周闻笙负责民俗、仪式和禁忌；陈泊舟负责外勤、撤离和保护。",
        "hidden_truth": "四人的功能位对应旧仪式的四个动作：记录、验证、命名、执行。灰卡不是随机选人，而是在把他们放回各自的位置。",
        "lock_level": "strict",
        "mutable_notes": "可以增加临时队友，但四人核心功能不要被替换。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "正典与线索渐进登记规则",
        "public_facts": "初始模板只固定主角团、灰卡机制、第一案起点和不可变边界。后续副本的大纲、真相、角色死亡、关键反转和读者反馈调整，必须在剧情确定后再登记为正典或线索。",
        "hidden_truth": "第七档案局的记录本身会被污染；过早写死未来副本会削弱连载调整空间，也容易造成认知预检误判。",
        "lock_level": "strict",
        "mutable_notes": "允许保留系列方向，但不把未来副本细节作为初始硬设定。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "每章戏剧任务规则",
        "public_facts": "每章生成前必须明确：角色想要什么、谁阻碍、读者期待什么、信息发生了什么变化、人物关系发生了什么变化、结尾留下什么钩子。正文只围绕这些任务推进。",
        "hidden_truth": "",
        "lock_level": "strict",
        "mutable_notes": "用于约束 PP 章节生成，避免散、顺、假和全知解释。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "正文信息边界",
        "public_facts": "正文只能写角色可感知、可推断、可误解的信息。禁止直接解释旧仪式、异常源本质和作者层真相。恐怖优先来自细节错位、证词互相抵触和日常秩序失效。",
        "hidden_truth": "",
        "lock_level": "absolute",
        "mutable_notes": "可用档案摘录、录音、照片、短信补信息，但也必须受角色认知限制。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "调查员属性与技能边界",
        "public_facts": "主角团每人有固定属性、固定核心技能和固定职责。技能可因剧情获得临时优势/惩罚，但不随副本自动升级；新能力必须来自明确训练、代价或道具。",
        "hidden_truth": "灰卡任务会通过失败和污染改变角色对技能的信心，而不是直接提升数值。",
        "lock_level": "strict",
        "mutable_notes": "后续可补每个角色的属性卡，但不要把技能写成网游式成长。",
        "status": "active",
    },
    {
        "canon_type": "artifact",
        "title": "核心道具与临时道具规则",
        "public_facts": "主角团每名成员至少绑定一个固定核心道具。核心道具可带出任务；损坏、遗失、污染必须触发惩罚。非核心道具只能在当前任务内使用，任务结束后不能带出，除非转化为证物并登记。",
        "hidden_truth": "核心道具并非单纯装备，而是角色在旧仪式中的位置锚点。道具受损会牵连记忆、关系、判断或下一次任务的安全余量。",
        "lock_level": "absolute",
        "mutable_notes": "非核心道具由剧情和道具识别自动生成；核心道具必须人工确认后登记。",
        "status": "active",
    },
    {
        "canon_type": "world_rule",
        "title": "主角团固定与关系遗忘",
        "public_facts": "主角团成员固定，不因单个副本随意换人。成员可能因为认知污染遗忘某段关系、某次救援或某个私人细节，但团队席位与职责保持稳定。",
        "hidden_truth": "关系遗忘是旧仪式削弱团队互证能力的方式；被忘记的关系仍会在道具、照片、录音和档案批注里留下痕迹。",
        "lock_level": "absolute",
        "mutable_notes": "允许失联、受伤、短期不信任，但不要无铺垫替换核心队员。",
        "status": "active",
    },
    {
        "canon_type": "other",
        "title": "第一副本：盐雾灯塔",
        "public_facts": "任务卡提示雾港东侧旧灯塔恢复亮灯，三名失踪者家属连续收到同一句短信：我在塔上，别让他们熄灯。白雨翔小组必须在涨潮前确认是否仍有生还者。",
        "hidden_truth": "灯塔不是单纯建筑，而是召回失败者的仪式标记。失踪者并非普通被困，他们中的一部分正在替下一批调查员守灯。",
        "lock_level": "strict",
        "mutable_notes": "第一案重点是建立灰卡、时限、误判、代价和主线回钩。",
        "status": "active",
    },
]

_FOG_HARBOR_CLUE_ITEMS: list[dict[str, Any]] = [
    {
        "clue_key": "fog-card-text-change",
        "clue_text": "灰卡上的任务文字会在无人注视时发生细微改写。",
        "visibility": "protagonist_known",
        "reveal_chapter": 1,
        "known_by": "白雨翔",
        "confidence": 0.9,
        "lock_level": "strict",
        "status": "active",
        "notes": "用于第一章制造任务不可靠感；正文不要解释灰卡来源。",
    },
    {
        "clue_key": "fog-bureau-hidden-file",
        "clue_text": "第七档案局存在未向白雨翔开放的旧任务档案。",
        "visibility": "reader_known",
        "reveal_chapter": 1,
        "known_by": "读者,白雨翔",
        "confidence": 0.78,
        "lock_level": "soft",
        "status": "active",
        "notes": "可以通过权限提示、被遮盖页码、上级打断来呈现。",
    },
    {
        "clue_key": "lighthouse-repeated-sms",
        "clue_text": "三名失踪者家属收到同一句短信：我在塔上，别让他们熄灯。",
        "visibility": "reader_known",
        "reveal_chapter": 1,
        "known_by": "白雨翔,许照,读者",
        "confidence": 0.86,
        "lock_level": "strict",
        "status": "active",
        "notes": "第一案开篇钩子；短信来源后置，不要开局解释。",
    },
    {
        "clue_key": "lighthouse-floor-count",
        "clue_text": "灯塔熄灯后楼层数量会变化，队员对楼梯段数的记忆互相冲突。",
        "visibility": "protagonist_known",
        "reveal_chapter": 1,
        "known_by": "白雨翔,陈泊舟",
        "confidence": 0.75,
        "lock_level": "strict",
        "status": "active",
        "notes": "用体感和对话呈现，不要写成旁白设定说明。",
    },
    {
        "clue_key": "lighthouse-fourth-footprint",
        "clue_text": "灯塔内有第四个人脚印，但失踪者资料只有三人。",
        "visibility": "protagonist_known",
        "reveal_chapter": 1,
        "known_by": "许照,白雨翔",
        "confidence": 0.8,
        "lock_level": "strict",
        "status": "active",
        "notes": "推动误判：第四人可能被认为是凶手或守灯人。",
    },
    {
        "clue_key": "lighthouse-tide-early",
        "clue_text": "潮汐时间比公开海事表提前，且提前幅度与灯塔熄灯次数相关。",
        "visibility": "reader_known",
        "reveal_chapter": 2,
        "known_by": "白雨翔,周闻笙,读者",
        "confidence": 0.72,
        "lock_level": "soft",
        "status": "active",
        "notes": "用于制造倒计时压力。",
    },
    {
        "clue_key": "keeper-is-replacement",
        "clue_text": "所谓守灯人不是一个固定的人，而是失败调查者被替换后的职位。",
        "visibility": "author_only",
        "reveal_chapter": None,
        "known_by": "作者",
        "confidence": 0.92,
        "lock_level": "absolute",
        "status": "active",
        "notes": "作者层真相，第一案只能通过照片、工牌、声音相似暗示。",
    },
    {
        "clue_key": "witness-ritual-mainline",
        "clue_text": "灰卡任务的真正目的不是救援，而是让白雨翔小组完成见证人训练。",
        "visibility": "author_only",
        "reveal_chapter": None,
        "known_by": "作者",
        "confidence": 0.95,
        "lock_level": "absolute",
        "status": "active",
        "notes": "主线底牌，严禁前期正文直出。",
    },
    {
        "clue_key": "white-old-memory-sealed",
        "clue_text": "白雨翔曾参与一次失败见证，相关记忆被第七档案局封存。",
        "visibility": "author_only",
        "reveal_chapter": None,
        "known_by": "作者",
        "confidence": 0.84,
        "lock_level": "absolute",
        "status": "active",
        "notes": "可先写成白雨翔对某些档案照片产生陌生熟悉感。",
    },
    {
        "clue_key": "bone-compass-cost",
        "clue_text": "骨罗盘能指向异常叙事中心，但使用后会短暂遗忘一个熟人的细节。",
        "visibility": "protagonist_known",
        "reveal_chapter": 2,
        "known_by": "周闻笙,白雨翔",
        "confidence": 0.76,
        "lock_level": "strict",
        "status": "active",
        "notes": "用于把道具代价落到人物关系，而不是数值。",
    },
    {
        "clue_key": "core-prop-loss-penalty",
        "clue_text": "核心道具损坏、遗失或被污染时，惩罚优先落在记忆、关系、判断或下一次任务安全余量上。",
        "visibility": "protagonist_known",
        "reveal_chapter": 1,
        "known_by": "白雨翔,许照,周闻笙,陈泊舟",
        "confidence": 0.82,
        "lock_level": "strict",
        "status": "active",
        "notes": "用于约束道具账本；不要把核心道具写成普通消耗品。",
    },
    {
        "clue_key": "temporary-props-cannot-exit",
        "clue_text": "副本内取得的非核心道具不能直接带出任务，除非被第七档案局转化为证物并登记。",
        "visibility": "protagonist_known",
        "reveal_chapter": 1,
        "known_by": "白雨翔,陈泊舟",
        "confidence": 0.78,
        "lock_level": "strict",
        "status": "active",
        "notes": "非核心道具仍可由剧情自动发现，但任务结束要清理或证物化。",
    },
    {
        "clue_key": "relationship-memory-loss",
        "clue_text": "主角团不会轻易换人，但可能遗忘彼此之间的某段共同经历或私人细节。",
        "visibility": "reader_known",
        "reveal_chapter": 2,
        "known_by": "白雨翔,读者",
        "confidence": 0.74,
        "lock_level": "strict",
        "status": "active",
        "notes": "关系遗忘要通过动作、称呼、旧照片和录音残留呈现。",
    },
    {
        "clue_key": "future-cases-progressive-registration",
        "clue_text": "后续副本的大纲、真相、核心线索和读者反馈调整，需要在剧情确定后再登记。",
        "visibility": "author_only",
        "reveal_chapter": None,
        "known_by": "作者",
        "confidence": 0.88,
        "lock_level": "strict",
        "status": "active",
        "notes": "这是创作流程约束，不是正文线索；防止初始模板过早锁死未来副本。",
    },
]

_FOG_HARBOR_PROP_ITEMS: list[dict[str, Any]] = [
    {
        "name": "灰卡",
        "category": "任务道具",
        "status": "可用；文字会自行改写",
        "current_holder": "白雨翔",
        "current_location": "随身证件夹",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "灰白色硬卡，无编号，背面偶尔浮出任务文字。它负责把小组送入异常现场。",
        "notes": "写到灰卡时必须保持不解释来源、不发奖励、不像游戏系统面板。",
    },
    {
        "name": "第七档案局封缄章",
        "category": "封缄工具",
        "status": "封存于外勤装备箱；需两人确认才能启用",
        "current_holder": "陈泊舟",
        "current_location": "第七档案局外勤装备箱",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "铜质印章，能短暂封住异常入口，但不能处理异常源。",
        "notes": "使用前要交代限制；使用后留下现实侧代价或记录污染。",
    },
    {
        "name": "盐蚀日志",
        "category": "档案证物",
        "status": "缺页；靠近海雾时纸页返潮",
        "current_holder": "白雨翔",
        "current_location": "第七档案局临时档案袋",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "旧守灯人日志，部分页码被盐渍糊住，能记录灯塔案的失败版本。",
        "notes": "适合在章末增加新字迹，作为下章钩子。",
    },
    {
        "name": "骨罗盘",
        "category": "异常工具",
        "status": "未启用；使用会造成短时记忆缺口",
        "current_holder": "周闻笙",
        "current_location": "黑布包",
        "first_seen_chapter": 2,
        "last_seen_chapter": 2,
        "importance": "major",
        "description": "指针由不明骨片制成，能指向异常叙事中心。",
        "notes": "每次使用必须付出具体记忆代价，不能当万能定位器。",
    },
    {
        "name": "黑线录音笔",
        "category": "证物",
        "status": "可录音；会录到现场不存在的第五人声音",
        "current_holder": "许照",
        "current_location": "证物包",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "外壳缠着黑色绝缘线的录音笔，用于保存证词和异常声纹。",
        "notes": "录音内容可以制造误导，但不能直接说出作者真相。",
    },
    {
        "name": "白雨翔的旧记者证",
        "category": "个人核心道具",
        "status": "边角磨损；照片背面有被刮掉的采访日期",
        "current_holder": "白雨翔",
        "current_location": "钱包夹层",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "白雨翔离开新闻行业前留下的证件，提醒他仍会本能追问证词来源。",
        "notes": "白雨翔固定核心道具。若损坏、遗失或污染，会触发记者时期记忆缺口，或让他误判证词来源。",
    },
    {
        "name": "空白证物袋",
        "category": "共享核心道具",
        "status": "未使用；每次任务限带三只",
        "current_holder": "第七档案局",
        "current_location": "外勤补给柜",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "用于把副本内的临时道具转化为可带出现实的证物。封口后会自动生成档案编号。",
        "notes": "不归属个人。若用完或污染，非核心道具不能带出任务。",
    },
    {
        "name": "雾港档案钥匙",
        "category": "共享核心道具",
        "status": "封存在局内；只在需要查阅封存档案时启用",
        "current_holder": "第七档案局",
        "current_location": "档案局内库",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "能打开部分被封存的旧案柜，但每次开启都会留下查阅者姓名和一段无法删除的批注。",
        "notes": "不归属个人。适合在中后段用于换取关键信息，同时暴露调查痕迹。",
    },
    {
        "name": "未命名黑匣",
        "category": "共享核心道具",
        "status": "禁止单独开启；当前封存在第七档案局",
        "current_holder": "第七档案局",
        "current_location": "负二层证物库",
        "first_seen_chapter": 1,
        "last_seen_chapter": 1,
        "importance": "major",
        "description": "可短暂保存异常声音、照片或文字的原始状态，避免证据在现实中被改写。",
        "notes": "不归属个人。若损坏，会导致一次已记录证据被现实侧覆盖。",
    },
]
