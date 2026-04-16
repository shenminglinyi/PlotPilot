"""
题材专属写作规则管理器
根据不同题材加载和管理写作规则
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class WritingRule:
    """单条写作规则"""
    type: str          # forbidden | style_positive | style_negative | rhythm | audit
    category: str       # 规则分类
    content: str        # 规则内容
    examples: List[str] = field(default_factory=list)  # 示例


@dataclass  
class GenreRules:
    """某题材的完整规则集"""
    genre: str
    name: str
    description: str
    forbidden: List[str]
    style_positive: List[str]
    style_negative: List[str]
    rhythm: Dict[str, Any]
    audit_dimensions: List[str]
    examples: List[Dict[str, str]]  # [{"bad": "...", "good": "..."}]
    
    def to_prompt(self) -> str:
        """转换为写作Prompt"""
        lines = [
            f"\n## 【{self.name}题材写作规则】",
            "",
            "### 禁止事项（出现即重写）",
        ]
        for item in self.forbidden:
            lines.append(f"- {item}")
        
        lines.extend([
            "",
            "### 应该这样做",
        ])
        for item in self.style_positive:
            lines.append(f"- ✅ {item}")
        
        lines.extend([
            "",
            "### 避免这样做",
        ])
        for item in self.style_negative:
            lines.append(f"- ❌ {item}")
        
        lines.extend([
            "",
            "### 节奏要求",
            f"- {self.rhythm.get('description', '')}",
        ])
        
        if self.examples:
            lines.extend([
                "",
                "### 写作示例"
            ])
            for i, ex in enumerate(self.examples, 1):
                lines.append(f"  ❌ 差例{i}：{ex['bad']}")
                lines.append(f"  ✅  好例{i}：{ex['good']}")
        
        return "\n".join(lines)


class GenreRulesManager:
    """题材规则管理器"""
    
    # 内置题材定义
    BUILTIN_GENRES = {
        "xuanhuan": {
            "name": "玄幻",
            "description": "以东方仙侠世界观为基础的奇幻小说，主角通过修炼获得力量",
            "forbidden": [
                "主角突破太快（每个大境界至少3章才能突破）",
                "同一场战斗超过3个势力参与",
                "女性角色只当花瓶或附属品",
                "宝物来历不明（需要独特来源和限制条件）",
                "境界压制写得过于简单（高境界对低境界应有碾压感但不是秒杀）",
                "主角永远有主角光环（需要合理的弱点和困境）",
                "战斗描写'秒天秒地'式（一招定胜负太无趣）",
                "升级靠外力（系统/丹药）而非自己的努力和领悟"
            ],
            "style_positive": [
                "战斗描写要有层次：试探→认真→底牌→逆转",
                "升级时描写能量涌动、境界压制、肉身蜕变",
                "宝物要有独特来历（传承/秘境/禁忌）和限制条件（认主/反噬/次数限制）",
                "配角要有自己的故事线，不只是工具人",
                "修炼体系要有清晰的等级和晋阶条件",
                "战斗前要有对峙和气势交锋",
                "每个重要配角的死都要有意义"
            ],
            "style_negative": [
                "避免'系统提示音'式升级（如'叮，恭喜宿主获得...'）",
                "不要写'莫欺少年穷'的简单重复",
                "不要让所有女性角色都爱上主角",
                "避免主角总是遇到巧合（命运安排要自然）"
            ],
            "rhythm": {
                "description": "战斗占比30%，修炼占比30%，日常占比20%，感情占比20%",
                "peaks": "每10章至少一个小高潮（战斗/突破），每30章一个大高潮（势力对决）"
            },
            "audit_dimensions": [
                "升级逻辑是否自洽（境界差不能太大，正常小境界差1-3个小境界可战）",
                "宝物设定是否前后矛盾",
                "打斗是否依赖主角光环（反杀需要合理铺垫）",
                "势力分布是否合理（大一统或碎片化都不合理）",
                "修炼资源是否稀缺（资源无限=无冲突）"
            ],
            "examples": [
                {
                    "bad": "主角大吼一声，使出全力，一剑将敌人斩成两半。",
                    "good": "主角牙关紧咬，经脉中的灵力如沸腾的岩浆般灼烧。他感觉到境界壁垒在颤抖——那是突破的征兆，但敌人不会给他时间。\n\n'给我破！'\n\n他强行冲击境界壁垒，一股狂暴的力量从体内炸开。剑光带着血芒斩出，敌人瞳孔骤缩——这是筑基后期的全力一击。"
                }
            ]
        },
        "urban": {
            "name": "都市",
            "description": "以现代都市为背景的现实主义小说",
            "forbidden": [
                "主角动不动就几亿身家（缺乏成长过程）",
                "反派智商下线（都市精英不会犯低级错误）",
                "所有有钱人都为富不仁（脸谱化）",
                "感情线太顺利（没有误会、没有阻碍）",
                "职场描写太理想化（现实职场有复杂的人际关系）",
                "主角开挂太多（系统/继承巨额遗产要合理）"
            ],
            "style_positive": [
                "场景描写要真实（地名/品牌/行为方式要符合实际）",
                "对话要像真人说话（有停顿、有废话、有潜台词）",
                "感情发展要有过程（不是一见钟情就海枯石烂）",
                "职场冲突要有专业性（不是靠嘴炮就能赢）",
                "配角要有自己的生活（不是围着主角转）",
                "主角的成长要有代价（时间/精力/人际关系）"
            ],
            "style_negative": [
                "不要写'霸道总裁'的套路（除非是反讽）",
                "不要写'所有人针对主角'的阴谋论",
                "避免'打脸'情节太多（偶尔爽一下可以，太多了就假）"
            ],
            "rhythm": {
                "description": "日常占比50%，感情占比30%，职场/事业占比20%",
                "peaks": "感情线和事业线交替推进，每20章一个转折点"
            },
            "audit_dimensions": [
                "场景描写是否符合现实（城市细节/职业细节）",
                "人物行为是否有现实逻辑",
                "感情线发展是否自然",
                "对话是否像真实的人说话"
            ],
            "examples": [
                {
                    "bad": "林总走进办公室，所有人都在讨论他。他冷冷地扫了一眼，然后走到自己的办公桌前坐下。",
                    "good": "林昭推门的时候，前台小妹的目光在他身上停了一秒——今天换了件没见过的衬衫。她低下头继续敲键盘，假装没注意到。\n\n'林工早。''早。'\n\n电梯口永远挤满了人。他看了眼表，还有七分钟，够了。"
                }
            ]
        },
        "xiuxian": {
            "name": "仙侠",
            "description": "以修仙问道为核心的主题，强调意境和道心",
            "forbidden": [
                "太暴力（仙侠讲究以柔克刚、以静制动）",
                "太功利（修仙者追求的是道，不是权势）",
                "人物太俗气（要有出尘之气）",
                "修炼太简单（顿悟需要心境配合）",
                "仙人太多（飞升者凤毛麟角）",
                "战斗太花哨（大道至简，一剑足矣）"
            ],
            "style_positive": [
                "语言要有意境（借景抒情、情景交融）",
                "修炼要讲心境（道心不稳则修为倒退）",
                "人物要有出尘气（不为俗世所动）",
                "战斗要讲道理（点到为止、不嗜杀）",
                "宝物要有灵性（能感应主人心意）",
                "天地要有规则感（天道无常但有迹可循）"
            ],
            "style_negative": [
                "避免'杀伐果断'的简单粗暴",
                "不要写修仙者争权夺利（偏离修道本意）",
                "不要写太多感情戏（仙侠的感情应该是含蓄的）"
            ],
            "rhythm": {
                "description": "修炼占比40%，悟道占比30%，游历占比20%，感情占比10%",
                "peaks": "悟道是最高潮，不需要激烈打斗"
            },
            "audit_dimensions": [
                "语言是否有仙侠意境",
                "人物是否有出尘气",
                "修炼是否讲心境",
                "战斗是否点到为止"
            ],
            "examples": [
                {
                    "bad": "他运起全身灵力，打出一掌，山崩地裂。",
                    "good": "他未曾拔剑，只是抬手。\n\n山风忽然停了。\n\n那片竹叶在半空中悬住，像时间被按下了暂停。他看着它坠落——不是落下，是被'收'进了某个看不见的地方。\n\n'这一招，我叫它'归去来'。'"
                }
            ]
        },
        "scifi": {
            "name": "科幻",
            "description": "以科学技术为核心推动力的幻想小说",
            "forbidden": [
                "科技设定违背已知物理定律（除非有明确设定）",
                "外星文明太人类化（应该有完全不同的思维方式）",
                "AI/机器人太像人（要有机械感）",
                "宇宙探索太简单（光速限制、费米悖论要面对）",
                "技术细节缺失（不能只说'高科技'）"
            ],
            "style_positive": [
                "科技描写要有细节（具体原理、工作方式）",
                "外星文明要有独特性（生理/文化/价值观差异）",
                "AI/机器人要有非人感（逻辑/情感模式不同于人类）",
                "宇宙要有尺度感（星际距离、时间跨度）",
                "技术有代价（高科技带来新问题）",
                "人物要有科学素养（专业领域的角色要懂行）"
            ],
            "style_negative": [
                "不要写'光速引擎'解决一切问题",
                "不要写'超级AI'总是想毁灭人类（老套）",
                "不要写外星人只是换了皮肤的人类"
            ],
            "rhythm": {
                "description": "科技探索占比40%，危机应对占比30%，人性探讨占比30%",
                "peaks": "科技与人性的冲突是核心张力"
            },
            "audit_dimensions": [
                "科技设定是否自洽",
                "物理定律是否被遵守（除非有说明）",
                "外星文明是否有独特性",
                "技术细节是否充分"
            ],
            "examples": [
                {
                    "bad": "飞船穿越虫洞，到达了另一个星系。",
                    "good": "中微子干涉仪的读数在第十三天出现异常。\n\n'不是设备问题。'她盯着屏幕，手指悬在控制台上方。'是真的——这里有一条裂缝。'\n\n三维投影亮起，空间在她面前折叠成一个不可能的形状。如果她的计算没错，这条裂缝的另一端，在六百光年之外。"
                }
            ]
        },
        "romance": {
            "name": "言情",
            "description": "以爱情为核心驱动力的情感小说",
            "forbidden": [
                "一见钟情就海枯石烂（需要过程）",
                "男/女主角完美无缺（要有缺点才真实）",
                "三角关系狗血（误会要有逻辑）",
                "反派总是坏事（现实感情问题更复杂）",
                "感情线发展太快（从相识到相守需要铺垫）"
            ],
            "style_positive": [
                "心理描写要细腻（心动要有层次）",
                "互动要有张力（欲言又止、口是心非）",
                "日常相处要有烟火气（不是只有浪漫）",
                "配角要有自己的感情线（丰富世界观）",
                "感情发展要有外部阻力（不是两个人之间的问题）",
                "分手/误会要有逻辑（不是为虐而虐）"
            ],
            "style_negative": [
                "不要写'霸道总裁'模板",
                "不要写'女主傻白甜'",
                "不要写'男二永远在等待'的备胎套路"
            ],
            "rhythm": {
                "description": "感情发展占比60%，日常占比30%，事业/其他占比10%",
                "peaks": "每次感情升温都需要一个小事件催化"
            },
            "audit_dimensions": [
                "心理描写是否细腻",
                "互动是否有张力",
                "感情发展是否自然",
                "配角是否立体"
            ],
            "examples": [
                {
                    "bad": "他看着她，心里有一种说不出的感觉。他知道她是自己这辈子最爱的人。",
                    "good": "他不知道该把目光放在哪里。\n\n她站在门口，手里还拿着那杯没喝完的咖啡，好像随时会转身离开。他想说什么，但喉咙像被什么堵住了。\n\n'我……'他开口。\n\n'嗯？'\n\n'……你咖啡洒了。'\n\n她的目光落在他身上，停顿了一秒。然后她笑了，那种让他不知所措的笑。"
                }
            ]
        }
    }
    
    # 通用规则（所有题材都适用）
    COMMON_RULES = {
        "name": "通用规则",
        "description": "适用于所有题材的基础写作规则",
        "forbidden": [
            "使用AI痕迹明显的词：'然而'、'因此'、'值得注意的是'、'实际上'、'综上所述'、'毋庸置疑'",
            "连续使用相同的句式开头",
            "在段尾写总结性/升华性的话",
            "用'是...的'结构描述动作（'他是慢慢走过去的'）",
            "过度使用成语（尤其是'不禁'、'不由自主'、'若有所思'）",
            "用'微微一笑'、'淡淡道'等套路化表情描写"
        ],
        "style_positive": [
            "长短句交错，避免整齐划一",
            "动作优先，用动词推动叙事",
            "对话要口语化，有停顿和潜台词",
            "用具体细节代替抽象描述",
            "描写时调用多个感官（视觉/听觉/嗅觉/触觉）",
            "场景转换时交代时间/地点变化"
        ],
        "style_negative": [
            "避免句式堆砌",
            "不要在段尾写'这让他明白了一个道理'",
            "不要用'他/她想'开头写心理描写（直接写行为）"
        ],
        "rhythm": {
            "description": "紧张段落后要有缓冲，不能连续5段都是高强度",
            "peaks": "高潮段落需要前面积累"
        },
        "audit_dimensions": [
            "AI痕迹检测",
            "句式变化",
            "对话自然度",
            "描写具体性"
        ],
        "examples": []
    }
    
    def __init__(self, custom_rules_dir: str = None):
        """
        初始化规则管理器
        
        Args:
            custom_rules_dir: 自定义规则目录（可选）
        """
        self.custom_rules_dir = Path(custom_rules_dir) if custom_rules_dir else None
        self._cache = {}
    
    def get_rules(self, genre: str) -> GenreRules:
        """
        获取某题材的完整规则
        
        Args:
            genre: 题材名（如'xuanhuan', 'urban'）
            
        Returns:
            GenreRules对象
        """
        if genre in self._cache:
            return self._cache[genre]
        
        # 先检查内置规则
        if genre in self.BUILTIN_GENRES:
            data = self.BUILTIN_GENRES[genre]
        elif self.custom_rules_dir:
            # 从自定义目录加载
            rule_file = self.custom_rules_dir / f"{genre}.yaml"
            if rule_file.exists():
                with open(rule_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            else:
                raise ValueError(f"未找到规则文件: {rule_file}")
        else:
            raise ValueError(f"未知的题材: {genre}，可用: {list(self.BUILTIN_GENRES.keys())}")
        
        rules = GenreRules(
            genre=genre,
            name=data.get("name", genre),
            description=data.get("description", ""),
            forbidden=data.get("forbidden", []),
            style_positive=data.get("style_positive", []),
            style_negative=data.get("style_negative", []),
            rhythm=data.get("rhythm", {}),
            audit_dimensions=data.get("audit_dimensions", []),
            examples=data.get("examples", [])
        )
        
        self._cache[genre] = rules
        return rules
    
    def get_common_rules(self) -> GenreRules:
        """获取通用规则"""
        return GenreRules(
            genre="common",
            name="通用规则",
            description="适用于所有题材",
            forbidden=self.COMMON_RULES["forbidden"],
            style_positive=self.COMMON_RULES["style_positive"],
            style_negative=self.COMMON_RULES["style_negative"],
            rhythm=self.COMMON_RULES["rhythm"],
            audit_dimensions=self.COMMON_RULES["audit_dimensions"],
            examples=self.COMMON_RULES["examples"]
        )
    
    def merge_genres(self, genres: List[str]) -> GenreRules:
        """
        合并多个题材的规则（用于混合题材）
        
        Args:
            genres: 题材列表，如['xuanhuan', 'romance']
        """
        all_forbidden = []
        all_positive = []
        all_negative = []
        all_audit = []
        
        common = self.get_common_rules()
        all_forbidden.extend(common.forbidden)
        all_positive.extend(common.style_positive)
        all_negative.extend(common.style_negative)
        all_audit.extend(common.audit_dimensions)
        
        for genre in genres:
            try:
                rules = self.get_rules(genre)
                all_forbidden.extend(rules.forbidden)
                all_positive.extend(rules.style_positive)
                all_negative.extend(rules.style_negative)
                all_audit.extend(rules.audit_dimensions)
            except ValueError:
                pass
        
        return GenreRules(
            genre="+".join(genres),
            name="/".join(genres),
            description=f"混合题材: {', '.join(genres)}",
            forbidden=all_forbidden,
            style_positive=all_positive,
            style_negative=all_negative,
            rhythm={"description": "综合多题材节奏要求"},
            audit_dimensions=all_audit,
            examples=[]
        )
    
    def generate_writing_prompt(
        self,
        genre: str,
        chapter_context: str = None,
        custom_constraints: List[str] = None,
        merge_genres: List[str] = None
    ) -> str:
        """
        生成完整的写作Prompt
        
        Args:
            genre: 题材
            chapter_context: 本章上下文/目标
            custom_constraints: 自定义约束
            merge_genres: 合并多个题材
        """
        # 获取规则
        if merge_genres:
            rules = self.merge_genres(merge_genres)
        else:
            common = self.get_common_rules()
            genre_rules = self.get_rules(genre)
            rules = genre_rules  # 题材规则已包含通用规则
        
        lines = [
            "## 写作规则",
            "",
            rules.to_prompt()
        ]
        
        if chapter_context:
            lines.extend([
                "",
                "## 本章背景",
                chapter_context
            ])
        
        if custom_constraints:
            lines.extend([
                "",
                "## 自定义约束",
                "以下约束优先级最高："
            ])
            for c in custom_constraints:
                lines.append(f"- {c}")
        
        lines.extend([
            "",
            "## 写作要求",
            "- 严格遵守禁止事项",
            "- 尽量遵循'应该这样做'的指导",
            "- 避免'避免这样做'中提到的问题",
            "- 如果字数超出目标，最多追加1次归一化，不硬截断"
        ])
        
        return "\n".join(lines)
    
    def list_genres(self) -> List[Dict[str, str]]:
        """列出所有可用的题材"""
        genres = []
        for key, data in self.BUILTIN_GENRES.items():
            genres.append({
                "id": key,
                "name": data["name"],
                "description": data["description"]
            })
        return genres
    
    def add_custom_genre(self, genre_id: str, data: Dict) -> None:
        """添加自定义题材规则"""
        self.BUILTIN_GENRES[genre_id] = data
        # 清除缓存
        if genre_id in self._cache:
            del self._cache[genre_id]


if __name__ == "__main__":
    manager = GenreRulesManager()
    
    print("可用题材:")
    for g in manager.list_genres():
        print(f"  {g['id']}: {g['name']} - {g['description']}")
    
    print("\n" + "=" * 50)
    
    # 生成玄幻题材的写作Prompt
    prompt = manager.generate_writing_prompt(
        genre="xuanhuan",
        chapter_context="本章主角林烬在师门大比中遭遇师兄压制，陷入绝境后突破",
        custom_constraints=["重点写主角的内心挣扎，不要写太多打斗"]
    )
    
    print(prompt[:1000])
