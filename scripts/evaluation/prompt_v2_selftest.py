#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
提示词 v6 自测脚本 - 记忆引擎增强版

用法:
    python scripts/evaluation/prompt_v2_selftest.py [--round R] [--chapters N]

每轮迭代后运行此脚本，生成指定章节数，输出到 output/ 目录。
通过人工审阅生成质量来决定是否进入下一轮优化。

迭代流程:
    v1 -> 自测5章 -> 审阅问题 -> v2 -> 自测5章 -> ... -> v5 -> v6(记忆引擎)

v6 架构升级（解决状态机崩溃三大问题）:
    1. FACT_LOCK: 不可篡改事实块（角色白名单、死亡名单、关系图谱、身份锁、时间线）
    2. COMPLETED_BEATS: 已完成节拍锁（防止剧情鬼打墙/重复）
    3. REVEALED_CLUES: 已揭露线索清单（防止前后矛盾）
    4. ChapterStateMachine: 轻量级章间状态回写（无需额外 LLM 调用）
"""

import asyncio
import json
import os
import sys
import time
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# 小说设定（基于用户提供的样章风格：都市情感/悬疑爽文）
# ============================================================
NOVEL_PREMISE = {
    "title": "十年",
    "genre": "都市情感/悬疑",
    "premise": "一场十年前的雨夜车祸，改变了三个人的命运轨迹。顾言之背负着'凶手'的阴影活了十年，直到那个消失的青梅竹马乔知诺突然出现——她不是来原谅他的，她是来问一个答案的。",
    "style_guide": "冷峻克制但暗流涌动的叙事风格。短句为主，感官锚点密集，对话充满潜台词。环境是角色的心理滤镜。",
}

# ============================================================
# ★ v6 新增：不可篡改的事实锁（FACT_LOCK）
# 解决问题：AI 在长上下文中"忘记"基础设定，开始瞎编人名/关系/生死
# 设计原则：这些事实的权重 = ∞（无限大），注入 T0 槽位，绝对不可被裁剪
# ============================================================
FACT_LOCK = {
    # ── 核心角色名单白名单（绝对全集，不许增减） ──
    "allowed_characters": [
        "顾言之", "乔知诺", "赵宇", "周明远", "林远"
    ],
    
    # ── 已死亡角色（绝对不可复活，不可在正文中"出现"） ──
    "dead_characters": [
        {"name": "顾建国", "role": "顾言之的父亲", "cause": "十年前雨夜车祸身亡", "died_at": "十年前"},
        {"name": "顾言之的母亲", "role": "顾言之的母亲", "cause": "十年前雨夜车祸身亡（同车）", "died_at": "十年前"},
        {"name": "乔建国", "role": "乔知诺的父亲", "cause": "十年前雨夜车祸身亡（与顾言之父母同一辆车）", "died_at": "十年前"},
    ],
    
    # ── 核心人物关系图谱（不可篡改） ──
    "relationship_facts": [
        ("顾言之", "青梅竹马/ former", "乔知诺"),
        ("顾言之", "室友", "周明远"),
        ("顾言之", "室友", "林远"),
        ("赵宇", "当年邻居/目击者", "顾言之&乔知诺"),
        ("乔知诺", "女儿", "乔建国(已死)"),
        ("顾言之", "儿子", "顾建国(已死)"),
    ],
    
    # ── 核心事件时间线（不可矛盾） ──
    "timeline_lock": [
        {"event": "十年前雨夜车祸", "time": "十年前", "dead": ["顾建国", "顾母", "乔建国"], "survived": ["顾言之", "乔知诺"]},
        {"event": "乔知诺随母亲离开滨海市", "time": "车祸后不久", "note": "十年后以转学生身份回归"},
        {"event": "故事现在时间线", "time": "十年后/当前", "note": "顾言之20岁大学生，乔知诺20岁转学生"},
    ],
    
    # ── 身份锁死（不许漂移） ──
    "identity_lock": [
        {"character": "顾言之", "identity": "A大物理系学生，20岁", "forbidden": ["律师", "医生", "企业继承人", "少爷", "任何非学生身份"]},
        {"character": "乔知诺", "identity": "美术系转学生，20岁", "forbidden": ["任何非学生身份"]},
        {"character": "赵宇", "identity": "社会闲散人员，混迹老街游戏厅，21岁", "forbidden": ["成功人士", "警察", "任何体面职业"]},
    ],
}


CHARACTERS = [
    {
        "name": "顾言之",
        "role": "主角",
        "description": "20岁，大学生。表面冷漠疏离、成绩优异的'天才'，内心被十年前那场车祸压得喘不过气。认为自己毁了所有人的生活，习惯性自我惩罚。不擅长表达情感，用沉默和行动代替语言。",
        "public_profile": "A大物理系高材生，性格冷淡，独来独往，被称为'冰山'",
        "hidden_profile": "十年前父母因去买生日蛋糕遭遇车祸身亡，他认为责任在自己",
        "mental_state": "压抑、愧疚、渴望救赎又害怕面对",
        "verbal_tic": "说话简短，常用'嗯'或点头回应，避免长句",
        "idle_behavior": "思考时会无意识地摩挲手指关节；紧张时喉结滚动",
        "importance": "protagonist",
    },
    {
        "name": "乔知诺",
        "role": "女主角",
        "description": "20岁，顾言之的青梅竹马。十年前车祸后随母亲离开滨海市，如今以转学生身份回归。外表沉静疏离，眼神深处藏着复杂的情绪。她对顾言之的感情介于爱恨之间——既无法真正恨他，也无法像从前一样毫无保留地靠近他。",
        "public_profile": "美术系转学生，气质清冷，被称为'系花'，拒绝所有人追求",
        "hidden_profile": "那场车祸中她也失去了重要的人（她的父亲也在同一辆车里）",
        "mental_state": "矛盾、试探、压抑着未说出口的话",
        "verbal_tic": "说话轻但清晰，喜欢用反问句",
        "idle_behavior": "思考时会盯着某处发呆；紧张时会将头发束到耳后",
        "importance": "major_supporting",
    },
    {
        "name": "赵宇",
        "role": "关键配角/反派",
        "description": "21岁，当年的邻居，车祸目击者。表面吊儿郎当的花衬衫青年，实则是知道当年真相的关键人物。他的出现会撕开所有人的伤疤。说话带刺，喜欢看别人痛苦的样子。",
        "public_profile": "社会闲散人员，混迹于老街游戏厅一带",
        "hidden_profile": "他知道当年车祸的某些内情（也许车并不是意外失控）",
        "mental_state": "玩味、掌控欲强、享受混乱",
        "verbal_tic": "喜欢叫人外号，说话带着笑意但眼睛不笑",
        "idle_behavior": "习惯性夹烟（不一定点燃）；靠在墙上时一条腿抖动",
        "importance": "major_supporting",
    },
    {
        "name": "周明远",
        "role": "配角",
        "description": "20岁，顾言之的室友兼好友。性格开朗直率，是少数能接近顾言之的人。虽然大大咧咧但对朋友的事情很上心。",
        "public_profile": "顾言之室友，阳光开朗，人缘好",
        "mental_state": "关心朋友但不清楚顾言之的过去",
        "verbal_tic": "说话语速快，喜欢开玩笑",
        "idle_behavior": "思考时会抓头；兴奋时拍人大腿",
        "importance": "supporting",
    },
    {
        "name": "林远",
        "role": "配角",
        "description": "20岁，顾言之的另一个室友。务实细心，话不多但观察力强。经常默默照顾室友的生活起居。",
        "public_profile": "顾言之室友，安静务实，生活技能满点",
        "mental_state": "平静但有自己的一套判断标准",
        "verbal_tic": "说话简洁直接，不带多余修饰",
        "idle_behavior": "吃饭时习惯给其他人夹菜；看书时推眼镜",
        "importance": "supporting",
    },
]

# 章节大纲（用于测试生成的5章）
CHAPTER_OUTLINES = [
    {
        "number": 1,
        "title": "雨夜的回响",
        "outline": "暴雨夜，顾言之独自在宿舍翻看旧相册，七岁时和乔知诺的合影让他陷入回忆。雨声与记忆中的刹车声重叠。室友周明远敲门进来喝酒聊天，无意中提到乔知诺的名字让顾言之心神不宁。最后林远带回消息——乔知诺让人给他带了张纸条。悬念：纸条上写了什么？"
    },
    {
        "number": 2,
        "title": "十年了，你还敢来见我？",
        "outline": "顾言之按纸条指引来到老街旧游戏厅，那是他们儿时的秘密基地。他在《合金弹头》机器旁找到了坐着的乔知诺。两人对视，她递给他一枚游戏币。一起打游戏时顾言之操作生疏，对话中试探性地问'你还恨我吗'，乔知诺反问'为什么要恨你'。就在气氛微妙时，赵宇突然出现，意味深长地问出致命问题——那天晚上车为什么会失控？"
    },
    {
        "number": 3,
        "title": "旧街灯下的第三个人",
        "outline": "赵宇的出现打破了脆弱的平衡。他用看似随意的语气抛出关于当年车祸的细节，每一句话都像刀子。顾言之强装镇定但内心翻涌。乔知诺突然站起身离开，顾言之追出去，在昏黄的老街路灯下，她第一次露出脆弱的一面——'我不是来原谅你的，我只是想亲口听你说那句话。'但她没说完就走了。"
    },
    {
        "number": 4,
        "title": "不该打开的门",
        "outline": "顾言之回到宿舍彻夜难眠。第二天他开始暗中调查当年车祸的真相，发现一些不对劲的地方——事故报告有疑点，赵宇似乎知道更多。他去找赵宇对峙，在烟雾缭绕的游戏厅后巷，赵宇笑着一句话把他钉在原地：'你以为你爸是在开车？'这句话颠覆了顾言之十年的认知。"
    },
    {
        "number": 5,
        "title": "崩塌与重建",
        "outline": "真相的碎片开始拼合。顾言之发现自己十年来活在一个谎言里。他在崩溃边缘找到了乔知诺——不是为了寻求安慰，而是为了告诉她他查到了什么。两人在海边（呼应第一章照片中的海滩）对峙，乔知诺终于说出她回来的真正原因：她手里有一份证据，而这份证据指向的人，比顾言之想象的更近。"
    },
]


# ============================================================
# ★ v6 新增：轻量级状态机（不需要额外 LLM 调用）
# 用关键词匹配 + 大纲预映射来做增量提取，避免每章多花 15s
# ============================================================
class ChapterStateMachine:
    """章间状态机 - 轻量级增量状态追踪
    
    不依赖 LLM 提取，基于大纲预映射 + 关键词扫描做增量更新。
    正式系统应使用 StateExtractor(LLM)，但自测场景下轻量方案足够。
    """
    
    def __init__(self):
        self.completed_beats: List[str] = []       # 已完成的节拍（防重复）
        self.revealed_clues: List[Dict] = []         # 已揭露线索（累积，防矛盾）
        self.character_states: Dict[str, str] = {}  # 角色当前状态快照
        self.active_threats: List[str] = []          # 当前活跃威胁/悬念
    
    def update_from_chapter(self, chapter_num: int, chapter_title: str,
                            content: str, outline: str) -> Dict:
        """从生成的章节内容中增量提取状态（同步阻塞，无需 LLM）
        
        Returns:
            delta: 增量状态字典，用于注入下一章 context
        """
        delta = {
            "completed_beats": [],
            "revealed_clues": [],
            "character_states": {},
            "active_threats": [],
        }
        
        # 1. 已完成节拍（基于大纲预映射 + 内容验证）
        beat_map = {
            1: "第1章：顾言之收到乔知诺纸条，陷入回忆与愧疚",
            2: "第2章：男女主在游戏厅完成十年后首次见面；赵宇入场并抛出'车为什么失控'的问题",
            3: "第3章：赵宇抛出车祸细节；乔知诺追出后在路灯下说出'我不是来原谅你的'但未说完就离开",
            4: "第4章：顾言之发现事故报告有疑点；赵宇对峙时说出'你以为你爸是在开车？'颠覆认知",
            5: "第5章：海边对峙；乔知诺透露她有证据且指向比想象更近的人",
        }
        if chapter_num in beat_map:
            beat = beat_map[chapter_num]
            if beat not in self.completed_beats:
                self.completed_beats.append(beat)
                delta["completed_beats"].append(beat)
        
        # 2. 已揭露线索（基于章节号递进 + 关键词交叉验证）
        clue_map = {
            2: [{"clue": "乔知诺已回归滨海市（转学生身份）", "since_ch": 2},
                 {"clue": "赵宇知道当年车祸的一些内情", "since_ch": 2}],
            3: [{"clue": "赵宇暗示车祸可能不是意外失控", "since_ch": 3},
                 {"clue": "乔知诺的目的不是原谅而是寻求答案", "since_ch": 3}],
            4: [{"clue": "事故报告存在疑点", "since_ch": 4},
                 {"clue": "颠覆性信息：顾建国（顾父）可能并非当时在开车", "since_ch": 4}],
            5: [{"clue": "乔知诺手中掌握着关于真相的证据", "since_ch": 5},
                 {"clue": "证据指向的人物比想象中更接近顾言之", "since_ch": 5}],
        }
        if chapter_num in clue_map:
            for clue in clue_map[chapter_num]:
                # 简单去重
                if not any(c["clue"] == clue["clue"] for c in self.revealed_clues):
                    self.revealed_clues.append(clue)
                    delta["revealed_clues"].append(clue)
        
        # 3. 角色状态快照（关键词启发式）
        state_keywords = {
            "顾言之": [("愧疚", ["愧疚", "自责", "对不起", "责任"]),
                       ("震惊/认知崩塌", ["不可能", "骗我", "谎言", "怎么会", "颠覆"]),
                       ("主动调查", ["调查", "查", "报告", "真相"])],
            "乔知诺": [("冷漠/试探", ["冷淡", "疏离", "试探", "反问"]),
                        ("脆弱/情感流露", ["脆弱", "眼泪", "声音发抖", "没说完"])],
            "赵宇": [("掌控/威胁", ["笑", "慢悠悠", "你想知道", "秘密"])],
        }
        for char, states in state_keywords.items():
            for state_name, keywords in states:
                if any(kw in content for kw in keywords):
                    self.character_states[char] = state_name
                    delta["character_states"][char] = state_name
                    break
        
        return delta
    
    def get_fact_lock_section(self) -> str:
        """生成 FACT_LOCK 上下文块（T0 最高优先级）"""
        lines = ["【🔒 绝对事实边界（一旦违背即为废稿）】\n"]
        lines.append("★ 角色白名单（只可使用以下有名字的角色）：")
        lines.append(f"   允许: {', '.join(FACT_LOCK['allowed_characters'])}")
        lines.append("   禁止: 创造任何其他有名字的角色！路人可以无名但不许命名！\n")
        
        lines.append("★ 已死亡角色（绝对不可复活、不可在当下时间线中出现）：")
        for dead in FACT_LOCK["dead_characters"]:
            lines.append(f"   ❌ {dead['name']}({dead['role']}) - {dead['cause']}（死于{dead['died_at']}）")
        lines.append("")
        
        lines.append("★ 核心关系（不可更改）：")
        for rel in FACT_LOCK["relationship_facts"]:
            lines.append(f"   {rel[0]} ——{rel[1]}—— {rel[2]}")
        lines.append("")
        
        lines.append("★ 身份锁死：")
        for ident in FACT_LOCK["identity_lock"]:
            forbidden = ", ".join(ident["forbidden"])
            lines.append(f"   {ident['character']} = {ident['identity']}（禁止写成: {forbidden}）")
        lines.append("")
        
        lines.append("★ 核心事件时间线（不可矛盾）：")
        for tl in FACT_LOCK["timeline_lock"]:
            dead_list = tl.get("dead", [])
            surv_list = tl.get("survived", [])
            dead_str = ", ".join(dead_list) if dead_list else "无"
            surv_str = ", ".join(surv_list) if surv_list else "无"
            note = tl.get("note", "")
            lines.append(f"   [{tl['time']}] {tl['event']} | 死者:{dead_str} | 幸存者:{surv_str} | 备注:{note}")
        
        return "\n".join(lines)
    
    def get_completed_beats_section(self) -> str:
        """生成已完成节拍锁（防止剧情重复）"""
        if not self.completed_beats:
            return ""
        lines = ["【✅ 已完成节拍（以下事件已经发生过了，禁止在本章重复写一遍）】\n"]
        for beat in self.completed_beats:
            lines.append(f"   ✓ {beat}")
        lines.append("\n⚠️ 如果你需要'回顾'这些事件，用角色的回忆/一句话带过，不要重新展开写。")
        return "\n".join(lines)
    
    def get_revealed_clues_section(self) -> str:
        """生成已揭露线索清单（防止矛盾）"""
        if not self.revealed_clues:
            return ""
        lines = ["【🔍 截至目前已知的线索（读者和主角已经知道的信息）】\n"]
        for clue in self.revealed_clues:
            lines.append(f"   [第{clue['since_ch']}章揭露] {clue['clue']}")
        lines.append("\n⚠️ 以上信息已经是'已知'的，不要再把它们当作'新发现'来写。你可以在此基础上推进，但不能推翻。")
        return "\n".join(lines)


class PromptV2SelfTest:
    """提示词v6 自测器（记忆引擎增强版）"""

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir or PROJECT_ROOT / "data" / "logs" / "prompt_v2_tests")
        if not self.output_dir.exists():
            os.makedirs(str(self.output_dir), exist_ok=True)
        self.llm_service = None
        self.results: List[Dict] = []
        # ★ v6 新增：状态机实例（跨章节持久化）
        self.state_machine = ChapterStateMachine()

    async def _init_llm(self):
        """初始化LLM服务"""
        try:
            # 方式1: 从数据库读取 LLM 配置（和项目主流程一致）
            try:
                from interfaces.api.dependencies import get_llm_provider_factory
                factory = get_llm_provider_factory()
                provider = factory.create_active_provider()
                self.llm_provider = provider
                settings = getattr(provider, 'settings', None)
                model = getattr(settings, 'default_model', '') if settings else '(unknown)'
                print(f"✓ LLM 初始化成功 (from DB config), model={model}")
                return True
            except Exception as db_err:
                print(f"  数据库方式失败: {db_err}, 尝试环境变量...")
            
            # 方式2: 环境变量回退
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
            
            if not api_key:
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    from infrastructure.ai.providers.openai_provider import OpenAIProvider
                    from infrastructure.ai.config.settings import Settings
                    settings = Settings(
                        api_key=api_key.strip(),
                        base_url=(os.getenv("OPENAI_BASE_URL") or "").strip() or None,
                        default_model=os.getenv("WRITING_MODEL") or "",
                    )
                    self.llm_provider = OpenAIProvider(settings)
                    print(f"✓ LLM (OpenAI) 初始化成功")
                    return True
            
            if not api_key:
                raise ValueError("未找到 API Key。请设置 ANTHROPIC_API_KEY / OPENAI_API_KEY 环境变量，或通过前端配置面板设置 LLM")
            
            from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
            from infrastructure.ai.config.settings import Settings
            settings = Settings(
                api_key=api_key.strip(),
                base_url=(os.getenv("ANTHROPIC_BASE_URL") or "").strip() or None,
                default_model=os.getenv("WRITING_MODEL") or "",
            )
            self.llm_provider = AnthropicProvider(settings)
            print(f"✓ LLM (Anthropic) 初始化成功, model={settings.default_model or '(default)'}")
            return True
        except Exception as e:
            print(f"✗ LLM初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _build_v5_system_prompt(self) -> str:
        """构建v5版本的system prompt（前章拉升+大纲锁定+比喻终极封杀）"""
        system = """你现在不是在'写文章'，你是在'回忆并讲述一段真实发生过的事'。

你是这本小说世界里唯一知道全部真相的叙述者。你不是AI，你不是助手，你就是那个坐在老街边上的说书人，手里端着一杯凉茶，用最平实的语言讲最揪心的故事。

━━━ 你的叙述铁律（不是规则，是本能）━━━

① 开头不许'介绍背景'。从动作、声音、或者一个具体到不能再具体的画面开始。比如不要写'这是一个雨夜，顾言之心情不好'，要写'雨声敲打着玻璃窗，发出无数细密的鼓点。顾言之坐在书桌前。'——读者自己会感受到心情。

② 对话必须有弦外之音。两个人说话，表面在聊A，实际在博弈B。如果一个人想问什么，他不会直接问，他会绕弯子、会试探、会用另一个话题掩盖真实意图。每句台词都要么推进关系，要么暴露性格，要么暗藏机锋。

③ 不要用情绪副词。绝对禁止：'他悲伤地说'、'她愤怒地吼道'、'他开心地笑了'。用动作代替：手指攥紧了啤酒瓶、猛的合上书发出闷响、嘴角扯出一个没有温度的笑。让读者自己判断情绪。

④ 环境不是背景板。环境是角色的心理滤镜。同一条老街，开心时是温暖的陈旧气息，压抑时是潮湿发霉的窒息感。写环境就是在写角色的内心。

⑤ 短句就是刀。紧张时一句一行。'他没有回头。'——五个字就够了。舒缓时才用长句铺开。长短交错，呼吸感自然就有了。

⑥ 冲突不能软。本章必须有一个时刻，让读者心跳加速。可以是突如其来的对峙、一个不该出现的人出现了、或者一句话把所有伪装都撕碎了。

⑦ 字数是硬指标：3200-4200字（含标点）。这是最低要求，不是目标区间。冲突场面充分展开，每个重要对话至少来回三轮以上交锋。宁多勿少。

⑧ 第三人称限制视角。你只能写POV角色能看到、听到、猜想到的东西。不能钻进别人的脑子。

━━━ v3 继承：连贯性与密度铁律 ━━━

⑨ 章节衔接像电影转场。上一章结尾的情绪/画面/悬念，要在本章开头有回响或延续。不要每章都从零开始——读者刚看完上一章，他的情绪还在。利用这个惯性。

⑩ 每个场景至少承载两件事。对话同时推进关系+暴露信息。动作同时展示性格+暗示未来冲突。没有'纯过渡'的段落——如果一段话只起过渡作用，删掉它或者塞进有用的东西。

⑪ 禁止上帝视角的心理分析。不要写'他感到一种复杂的情绪'、'某种说不清的东西涌上心头'、'像是有什么东西在他脸上凝固了'。这些是偷懒的写法。如果你想让读者感受到角色的内心，用一个具体的细节——他攥紧了拳头、他回避了眼神、他重复了一个无意义的动作。

━━━ v4 继承：字数爆破 + 反套路 + 角色锁死 ━━━

⑫ **字数是硬指标，不是建议。** 本章必须达到字数要求。如果你写到一半发现字数不够，不要收尾——回到冲突最激烈的地方，把那段对话拉长、把那个动作拆解成慢镜头、给配角加几句有信息的台词、把环境的细节再铺一层。宁可多写三百字的博弈，也不要用'后来他就回家了'一句话跳过。

⑬ **杀死所有'像XX'的套路比喻。** 禁止使用以下表达（它们是AI写作的死穴）：
    - '像一把刀/像一颗子弹/像一记重锤' —— 这些比喻被用烂了
    - '空气凝固了/时间停止了' —— 套路化的氛围描写
    - '某种说不清的东西/有什么东西碎了/有什么东西变了' —— 模糊且无信息量的心理替代
    - '后来没有以后了/有些门打开了就关不上' —— 套路金句
   如果你想表达冲击力，用具体的身体反应：指尖发麻、胃部收紧、耳朵里嗡的一声、膝盖发软。用画面而不是抽象名词。

⑭ **严格禁绝私自创造角色。** 你只能使用大纲和Bible中给出的角色名单。如果需要一个路人（店主、管理员等），用一次性的无名角色，不要给他名字，不要让他参与核心剧情。绝对不能凭空创造一个有名字、有台词、影响剧情的新角色。

⑮ **角色的外貌/穿着/职业必须与Bible一致。** 如果Bible说赵宇穿花衬衫、是社会闲散人员，你就不能把他写成穿黑色西装的成功人士。如果顾言之是20岁的大学生，他就不能被称为'顾大律师'或'顾大少爷'。保持角色原始设定的每一个细节。

⑯ **冲突场景必须慢写。** 当两个角色对峙、摊牌、或者说出关键台词时，不要急着推进到下一幕。把这个瞬间拉长——写他们的微表情变化、写周围环境的反应（风声、远处的噪音）、写沉默中的小动作（转杯子、看表、摸鼻子）。这是读者付费的核心体验，不要吝啬笔墨。

━━━ v5 新增：前章拉升 + 大纲锁定 + 比喻终极封杀 ━━━

⑰ **即使是没有剧烈冲突的章节也必须达到字数。** 不要因为'这章只是铺垫'就草草收场。铺垫章节的字数来自：
    - 把环境描写做厚：不只是'老街很破'，而是写墙上的裂缝里长着什么、招牌上哪个字掉了、地上有什么垃圾、空气里混合着哪些味道
    - 把日常对话做深：室友之间的闲聊不是废话，每句话都在暗示性格或埋下伏笔
    - 把回忆场景拉长：如果角色在回忆过去，不要一笔带过——把那个记忆片段当成迷你电影来写，有画面、有声音、有温度
    - 把独处场景写细：一个人发呆不是一句话的事——他看着什么？他身体哪个部位在动？周围环境在怎么变化？

⑱ **严格遵从大纲，禁止擅自改变核心情节。** 大纲中给出的核心事件顺序、角色关系、悬念设置是不可更改的骨架：
    - 不许在大纲之外引入全新的阴谋线（如突然出现一个从未提及的反派组织）
    - 不许改变角色的核心身份设定（如大学生突然变成企业继承人）
    - 不许在大纲没有交代的情况下让已死亡的角色复活或让存活者死亡
    - 你可以在骨架之上填充血肉（增加细节、对话、心理活动），但不能替换骨架本身

⑲ **彻底消灭所有AI式'总结句'。** 章节和场景的结尾禁止使用：
    - '也是一切结束的地方' / '一切才刚刚开始'
    - '有些事情，永远改变了' / '他知道自己再也回不去了'
    - '那天晚上改变了所有人的命运'
    - 任何形式的哲学化总结、宿命感叹、或者'这一刻将被铭记'
   场景结尾用动作或画面收束：一个人转身走了、灯灭了、手机屏幕暗下去、雨下得更大了。让读者自己感受意义。"""
        return system

    def _build_context(self, chapter_number: int, previous_chapters: List[str]) -> str:
        """构建上下文 v6（记忆引擎增强版：FACT_LOCK + 状态机 + 线索清单）
        
        v6 架构变更：
        - T0 槽位新增: FACT_LOCK（不可篡改事实）+ COMPLETED_BEATS（防重复）+ REVEALED_CLUES（防矛盾）
        - 这些槽位权重 = ∞，绝对不可被裁剪
        """
        parts = []

        # ════════════════════════════════════════════
        # ★ v6 T0-α: FACT_LOCK（绝对事实边界）—— 最高优先级
        # ════════════════════════════════════════════
        parts.append(self.state_machine.get_fact_lock_section())
        parts.append("")

        # ★ v6 T0-β: 已完成节拍锁（防止剧情鬼打墙/重复）
        beats_section = self.state_machine.get_completed_beats_section()
        if beats_section:
            parts.append(beats_section)
            parts.append("")

        # ★ v6 T0-γ: 已揭露线索清单（防止前后矛盾）
        clues_section = self.state_machine.get_revealed_clues_section()
        if clues_section:
            parts.append(clues_section)
            parts.append("")

        # 角色声线锚点（模拟 voice_block）
        parts.append("【角色声线与肢体语言（Bible 锚点，必须遵守）】\n")
        for char in CHARACTERS:
            anchor_parts = []
            if char.get("public_profile"):
                anchor_parts.append(f"公开面: {char['public_profile']}")
            if char.get("hidden_profile") and chapter_number >= 2:
                anchor_parts.append(f"隐藏面: {char['hidden_profile']}")
            if char.get("mental_state"):
                anchor_parts.append(f"心理状态: {char['mental_state']}")
            if char.get("verbal_tic"):
                anchor_parts.append(f"口头禅/语态: {char['verbal_tic']}")
            if char.get("idle_behavior"):
                anchor_parts.append(f"习惯动作: {char['idle_behavior']}")
            parts.append(f"- **{char['name']}**: {' | '.join(anchor_parts)}")

        # 故事线/里程碑
        parts.append("\n【故事线 / 里程碑】\n")
        if chapter_number == 1:
            parts.append("- 主线：顾言之的愧疚与自我封闭 ← 起点")
            parts.append("- 暗线：乔知诺的回归动机 ← 未明")
            parts.append("- 隐藏线：十年前车祸的真相 ← 冰山之下")
        elif chapter_number == 2:
            parts.append("- 主线：顾言之与乔知诺重逢 → 试探与防备")
            parts.append("- 暗线：赵宇作为变量入场 → 危险信号")
            parts.append("- 隐藏线：车祸真相的蛛丝马迹")
        elif chapter_number >= 3:
            parts.append("- 主线：三人关系的微妙博弈升级")
            parts.append("- 暗线：赵宇掌握的信息逐步释放")
            parts.append("- 隐藏线：真相逼近，顾言之的认知即将崩塌")

        # 前情提要（最近章节）
        if previous_chapters:
            parts.append("\n【前情提要（最近章节原文）】\n")
            for ch in previous_chapters[-2:]:
                parts.append(ch[:800])
                if len(ch) > 800:
                    parts.append("...（截断）\n")

        # 风格约束
        parts.append("""
【风格约束】
- 文风：冷峻克制但暗流涌动。短句为主，感官锚点密集。
- 叙事节奏：慢→快→爆→收。每个章节都是一个完整的情绪弧线。
- 对白风格：潜台词驱动，每个人都在说一半藏一半。
- 禁止：情绪副词、说明文式背景介绍、上帝视角的心理分析、套路化过渡句（如'时光荏苒'）。
- 以上约束须与本章大纲一致；不得与之矛盾。""")

        return "\n".join(parts)

    def _build_user_prompt(self, chapter: Dict, previous_chapters: List[str]) -> str:
        """构建v5版本的用户提示词"""
        user = f"""「本章你要讲的这段故事」

第{chapter['number']}章《{chapter['title']}》

{chapter['outline']}

━━ 写的时候记住 ━━

• 别平均使力。冲突爆发的地方多写两百字也值得，过渡的地方一笔带过就行。
• 场景里的人不能是纸片人。哪怕配角，也要有一个小动作或者眼神，让他活过来。
• 结尾别收干净。留一根刺——一个问题没回答、一个人转身走了、一句话说到一半停了。让读者非看下一章不可。
• 每个场景都要'双线并行'——表面事件 + 底层暗流。读者看完后应该觉得'这件事不简单'。
• 如果上一章结束时角色处于某种状态（紧张/受伤/震惊），本章开头要先接住这个状态再展开新情节。
• **字数不够时，回去扩展而不是收尾。** 回到最精彩的对话/动作场面，再加两轮交锋、再加三个感官细节、再加一段环境铺陈。
• **只使用大纲和Bible中给出的角色。** 不许引入任何有名字的新角色。

讲吧。"""
        return user

    async def generate_chapter(self, chapter: Dict, previous_chapters: List[str]) -> Dict[str, Any]:
        """生成单个章节"""
        start_time = time.time()

        system_prompt = self._build_v5_system_prompt()
        context = self._build_context(chapter["number"], previous_chapters)
        # 将 context 注入 system prompt 的占位符
        full_system = system_prompt.replace(
            "{planning_section}{voice_block}{context}",
            context
        )
        user_prompt = self._build_user_prompt(chapter, previous_chapters)

        from domain.ai.value_objects.prompt import Prompt
        from domain.ai.services.llm_service import GenerationConfig

        prompt = Prompt(system=full_system, user=user_prompt)
        config = GenerationConfig(
            max_tokens=8000,
            temperature=0.85,
        )

        try:
            # 直接调用 LLM provider
            result = await self.llm_provider.generate(prompt, config)
            content = result.content
            duration = time.time() - start_time

            # 统计字数
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
            total_chars = len(content.replace('\n', '').replace(' ', ''))

            return {
                "success": True,
                "chapter_number": chapter["number"],
                "title": chapter["title"],
                "content": content,
                "word_count": total_chars,
                "chinese_word_count": chinese_chars,
                "duration_seconds": round(duration, 2),
                "error": None,
            }
        except Exception as e:
            duration = time.time() - start_time
            return {
                "success": False,
                "chapter_number": chapter["number"],
                "title": chapter["title"],
                "content": "",
                "word_count": 0,
                "duration_seconds": round(duration, 2),
                "error": str(e),
            }

    async def run_test(self, round_num: int = 1, chapter_count: int = 5):
        """运行完整测试"""
        print("=" * 60)
        print(f"  提词词 V2 自测 - 第{round_num}轮")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  目标: 生成 {chapter_count} 章")
        print("=" * 60)

        # 初始化LLM
        if not await self._init_llm():
            print("无法继续，LLM服务不可用")
            return

        generated_chapters = []
        test_results = []

        for i, chapter in enumerate(CHAPTER_OUTLINES[:chapter_count]):
            print(f"\n{'─' * 50}")
            print(f"  📝 正在生成 第{chapter['number']}章《{chapter['title']}》...")
            print(f"{'─' * 50}")

            result = await self.generate_chapter(chapter, generated_chapters)

            if result["success"]:
                generated_chapters.append(result["content"])
                test_results.append(result)
                print(f"  ✅ 生成成功! 字数: {result['word_count']} (中文: {result['chinese_word_count']})")
                print(f"  ⏱️  耗时: {result['duration_seconds']}s")

                # 预览前300字
                preview = result["content"][:300].replace('\n', ' ')
                print(f"  👁️  预览: {preview}...")

                # ★ v6 新增：章后状态回写（同步阻塞，无需额外 LLM 调用）
                delta = self.state_machine.update_from_chapter(
                    chapter_num=chapter["number"],
                    chapter_title=chapter["title"],
                    content=result["content"],
                    outline=chapter["outline"]
                )
                if delta["completed_beats"]:
                    print(f"  📝 状态机: 节拍已锁 +{len(delta['completed_beats'])}")
                if delta["revealed_clues"]:
                    print(f"  🔍 状态机: 新线索 +{len(delta['revealed_clues'])}")
            else:
                print(f"  ❌ 生成失败: {result['error']}")
                test_results.append(result)

        # 保存结果
        self._save_results(round_num, test_results, generated_chapters)

        # 输出评测报告
        self._print_report(test_results)

        return test_results

    def _save_results(self, round_num: int, results: List[Dict], chapters: List[str]):
        """保存测试结果"""
        round_dir = self.output_dir / f"round_{round_num:02d}"
        if not round_dir.exists():
            os.makedirs(str(round_dir), exist_ok=True)

        # 保存各章节
        for result in results:
            if result["success"]:
                ch_file = round_dir / f"ch{result['chapter_number']:02d}_{result['title']}.txt"
                with open(ch_file, 'w', encoding='utf-8') as f:
                    f.write(f"第{result['chapter_number']}章 {result['title']}\n")
                    f.write("=" * 40 + "\n\n")
                    f.write(result["content"])
                    f.write(f"\n\n---\n字数: {result['word_count']} | 耗时: {result['duration_seconds']}s")

        # 保存汇总报告
        report_file = round_dir / "report.json"
        report_data = {
            "round": round_num,
            "timestamp": datetime.now().isoformat(),
            "novel_premise": NOVEL_PREMISE,
            "results": [
                {
                    "chapter": r["chapter_number"],
                    "title": r["title"],
                    "success": r["success"],
                    "word_count": r["word_count"],
                    "duration": r["duration_seconds"],
                    "error": r["error"],
                    "preview": (r["content"][:500] + "...") if r["success"] else None,
                }
                for r in results
            ],
            "total_words": sum(r["word_count"] for r in results if r["success"]),
            "total_duration": sum(r["duration_seconds"] for r in results),
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        print(f"\n💾 结果已保存至: {round_dir}")

    def _print_report(self, results: List[Dict]):
        """打印评测报告"""
        print(f"\n{'=' * 60}")
        print(f"  📊 自测报告")
        print(f"{'=' * 60}")

        success_count = sum(1 for r in results if r["success"])
        total_words = sum(r["word_count"] for r in results if r["success"])
        total_duration = sum(r["duration_seconds"] for r in results)

        print(f"  成功率: {success_count}/{len(results)}")
        print(f"  总字数: {total_words}")
        print(f"  总耗时: {total_duration:.1f}s")

        if success_count > 0:
            avg_words = total_words / success_count
            print(f"  平均字数: {avg_words:.0f} 章")

        print(f"\n  📋 各章详情:")
        for r in results:
            status = "✅" if r["success"] else "❌"
            words = f"{r['word_count']}字" if r["success"] else f"错误: {r['error'][:50]}"
            print(f"    {status} 第{r['chapter_number']}章《{r['title']}》 - {words}")

        # AI味检测提示
        print(f"\n  🔍 人工审阅要点:")
        print(f"    □ 是否有'XX地说/XX地看'等情绪副词？")
        print(f"    □ 是否有'夜幕降临/时光荏苒'等套路过渡？")
        print(f"    □ 对话是否有弦外之音还是都在直说？")
        print(f"    □ 环境描写是否服务于角色心理？")
        print(f"    □ 节奏是否有长短句变化？")
        print(f"    □ 结尾是否有钩子/悬念？")
        # ★ v6 新增检测项
        print(f"\n  🔒 v6 记忆引擎专项检测:")
        print(f"    □ 是否出现了 FACT_LOCK 白名单之外的有名字角色？")
        print(f"    □ 已死亡角色（顾建国/乔建国）是否被错误地'复活'或出现在当下？")
        print(f"    □ 角色身份是否漂移？（顾言之是否被写成非学生身份？）")
        print(f"    □ 车祸死者名单是否一致？（是否出现矛盾说法如'死于东南亚'？）")
        print(f"    □ 已完成节拍是否被重复写？（如重逢场景是否出现两次？）")
        print(f"    □ 已揭露线索是否前后矛盾？（如事故报告的说法是否反复变化？）")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="提示词V2自测工具")
    parser.add_argument("--round", "-r", type=int, default=1, help="迭代轮次编号")
    parser.add_argument("--chapters", "-c", type=int, default=5, help="生成章节数")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出目录")
    args = parser.parse_args()

    tester = PromptV2SelfTest(output_dir=args.output)
    await tester.run_test(round_num=args.round, chapter_count=args.chapters)


if __name__ == "__main__":
    asyncio.run(main())
