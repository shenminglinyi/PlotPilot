# application/audit/services/cliche_scanner.py
"""增强版俗套句式扫描器 — 覆盖用户规则集中的全部禁用模式。

从原有10个模式扩展至35+模式，覆盖：
- 微表情/微动作（嘴角上扬、眼里闪过、指尖泛白、一丝系列等）
- 声线/语气描述（带着XX口吻、不容置疑等）
- 比喻句式（仿佛、宛如、犹如、心湖涟漪等）
- 生理性系列（生理性泪水、生理性前缀等）
- 情绪标签（直接情绪标签、心中波澜等）
- 句式（不是而是、破折号等）
- 小动物比喻
- 面部大忌、身体大忌
- 其他AI高频俗套
"""
import re
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional


@dataclass
class ClicheHit:
    """俗套句式命中结果（增强版）"""
    pattern: str       # 匹配的模式名称
    text: str          # 匹配的文本
    start: int         # 起始位置
    end: int           # 结束位置
    severity: str = "warning"     # "critical" | "warning" | "info"
    category: str = ""            # 分类标签
    replacement_hint: str = ""    # 替换建议


# ─── 增强版 AI 生成文本俗套检测模式 ───
# 格式：(正则, 模式名, 严重性, 分类, 替换建议)
AI_CLICHE_PATTERNS_ENHANCED: List[Tuple[str, str, str, str, str]] = [
    # ═══ 原有 10 模式保留 ═══
    (r"熊熊(烈火|怒火|火焰|燃烧)", "熊熊系列", "warning", "俗套", "用具体描写替代"),
    (r"(眼中|眸中|目光中)闪过一丝", "眼神闪过系列", "critical", "微表情", "用对话或动作替代"),
    (r"嘴角(勾起|扬起|浮现|上扬).*?[笑弧]", "嘴角笑意系列", "critical", "微表情", "写完整姿态变化或不写"),
    (r"(心中|内心)五味杂陈", "五味杂陈系列", "warning", "情绪", "通过动作暗示"),
    (r"如同.{1,10}一般", "如同一般系列", "critical", "比喻", "用感官细节替代比喻"),
    (r"(眼神|目光|气势).{0,3}(变得|显得|愈发)?凌厉", "凌厉系列", "warning", "俗套", "用具体描写替代"),
    (r"(眼神|目光|眼中).{0,5}复杂", "复杂眼神系列", "warning", "微表情", "用具体动作替代"),
    (r"(内心|心中).{0,5}(泛起|涌起|掀起).{0,5}波澜", "心中波澜系列", "critical", "情绪", "通过动作暗示"),
    (r"(眼神|目光|眼眸).{0,3}(深邃|幽深)", "深邃眼神系列", "warning", "俗套", "用具体描写替代"),
    (r"(嘴角|脸上|眼中).{0,3}(浮现|闪过|掠过)一抹", "一抹系列", "warning", "俗套", "用具体动作替代"),

    # ═══ 微表情/微动作 ═══
    (r"嘴角(勾起|上扬|扬起|浮现|翘起)", "嘴角微表情", "critical", "微表情", "写完整姿态变化"),
    (r"眼里(闪过|显现出|漾起).{0,6}(光芒|光|星光|温柔)", "眼里闪过", "critical", "微表情", "用对话或动作替代"),
    (r"(指尖|指节)(泛白|发白)", "指尖泛白", "critical", "微表情", "用行为传递紧张感"),
    (r"(下意识|无意识地?)", "下意识/无意识", "warning", "微表情", "写完整的动作链"),
    (r"一丝.{0,4}(笑意|暖意|寒意|警惕|不易察觉)", "一丝系列", "warning", "微表情", "要么具体到可感知，要么别写"),
    (r"不易察觉", "不易察觉", "warning", "微表情", "如果不易察觉，读者怎么知道？"),

    # ═══ 声线/语气描述 ═══
    (r"带着.{1,8}(口吻|语气)", "带语气前缀", "critical", "声线", "用对白本身的标点和断句表现语气"),
    (r"(声音|语调).{0,5}(变得|比.{1,4}更).{0,5}(冰冷|低沉|凌厉)", "声线变化", "critical", "声线", "让对白内容自己说话"),
    (r"每一个字都带着", "字字带X", "critical", "声线", "删掉这句话，让对白自身有力度"),
    (r"不容(置疑|置喙)", "不容置疑", "critical", "声线", "用对白本身的力度表现权威"),
    (r"用.{1,6}的语气", "用XX语气", "critical", "声线", "用对白标点和断句"),
    (r"充满了.{1,6}的味道", "充满XX味道", "warning", "声线", "用对白本身表现"),
    (r"声音比.{1,6}更冰冷", "声音比XX冰冷", "critical", "声线", "删掉，让对白自身有力度"),
    (r"话语充满.{1,4}气", "话语充满X气", "warning", "声线", "用具体用词表现"),

    # ═══ 比喻句式 ═══
    (r"(仿佛|宛如|犹如|恰似|酷似).{1,15}(般|一般|似的|一样)", "比喻句式", "critical", "比喻", "用感官细节替代比喻"),
    (r"如同.{1,12}(一般|一样)", "如同比喻", "critical", "比喻", "用感官细节替代比喻"),
    (r".{1,6}像.{1,4}投入.{1,6}(心湖|水面).{0,6}(泛起|荡起|漾起)涟漪", "心湖涟漪", "critical", "比喻", "禁止此意象，用具体动作"),
    (r"投入.{0,6}(心湖|水面)", "投入心湖", "critical", "比喻", "禁止心湖意象"),
    (r"(泛起|荡起|漾起)涟漪", "涟漪意象", "critical", "比喻", "禁止涟漪意象"),

    # ═══ 生理性系列 ═══
    (r"生理性(泪水|水雾|液体|汽水|盐水)", "生理性液体", "critical", "生理", "直接描述哭泣的差异化写法"),
    (r"生理性", "生理性前缀", "critical", "生理", "删掉'生理性'，直接写反应"),

    # ═══ 情绪标签 ═══
    (r"(感到|觉得|心中|内心)(非常|极度|无比)?(愤怒|悲伤|恐惧|厌恶|惊讶|喜悦|痛苦)", "直接情绪标签", "warning", "情绪", "通过动作/环境暗示"),

    # ═══ 句式 ═══
    (r"不是[^。，？！]{1,20}(而是|只是)", "不是而是句式", "warning", "句式", "转为直接叙述"),
    (r"——", "破折号", "warning", "句式", "正文用句号替代，对话中可保留"),

    # ═══ 小动物比喻 ═══
    (r"像(小兔子|小鹿|小猫|小兽|幼兽)", "小动物比喻", "critical", "比喻", "禁止动物比喻，用具体动作"),

    # ═══ 比喻意象 ═══
    (r"精致人偶", "精致人偶", "critical", "比喻", "用具体的外貌/姿态描写"),

    # ═══ 面部大忌 ═══
    (r"眸色一沉|眼神暗了暗|眉头微皱|邪魅一笑|似笑非笑", "面部大忌", "critical", "俗套", "用动作或对白替代"),
    (r"(眼神|目光).{0,3}冰冷", "眼神冰冷", "critical", "俗套", "写对话时的具体反应"),
    (r"深邃", "深邃", "warning", "俗套", "删除或用具体描述"),

    # ═══ 身体大忌 ═══
    (r"呼吸一滞|倒吸一口凉气|喉结微滚|浑身一震|身子一僵", "身体大忌", "critical", "俗套", "用差异化反应替代"),
    (r"四肢百骸", "四肢百骸", "critical", "俗套", "用具体的身体部位描述"),
    (r"青筋暴起", "青筋暴起", "critical", "俗套", "写紧握的物体变形/碎裂"),

    # ═══ 严禁词 ═══
    (r"死死", "死死", "critical", "严禁词", "删除或换词"),

    # ═══ 其他 AI 高频俗套 ═══
    (r"毫不夸张地说", "毫不夸张", "warning", "俗套", "删掉"),
    (r"(熊熊|滔滔不绝|如同实质般)", "经典俗套", "warning", "俗套", "用具体描写替代"),
    (r"虔诚|膜拜", "虔诚/膜拜", "warning", "俗套", "用具体行为替代"),

    # ═══ 数字比喻 ═══
    (r"[三四五六七八九]分[^，。]{1,6}[七八九]分", "数字比喻", "warning", "俗套", "删除数字量化"),

    # ═══ 仿佛一折就断等短语 ═══
    (r"精密仪器", "精密仪器比喻", "warning", "比喻", "用具体的精确描述"),
    (r"轻描淡写", "轻描淡写", "warning", "俗套", "写具体的无所谓的动作"),
    (r"仿佛一折就断", "仿佛一折就断", "critical", "比喻", "写具体的脆弱表现"),
    (r"角落上扬露出一丝微笑", "嘴角微笑组合", "critical", "微表情", "写完整姿态或不写"),
]


class ClicheScanner:
    """增强版俗套句式扫描器

    使用正则表达式检测 AI 生成文本中的常见俗套句式。
    支持三种严重级别：critical / warning / info
    支持分类统计和替换建议。
    """

    def __init__(self, use_enhanced: bool = True):
        """初始化扫描器

        Args:
            use_enhanced: 是否使用增强版模式（默认 True）
        """
        if use_enhanced:
            raw_patterns = AI_CLICHE_PATTERNS_ENHANCED
            self.compiled_patterns = [
                (re.compile(pattern), name, severity, category, hint)
                for pattern, name, severity, category, hint in raw_patterns
            ]
        else:
            # 兼容旧版：仅使用原有 10 个模式
            legacy_patterns = [
                (r"熊熊(烈火|怒火|火焰|燃烧)", "熊熊系列"),
                (r"(眼中|眸中|目光中)闪过一丝", "眼神闪过系列"),
                (r"嘴角(勾起|扬起|浮现|上扬).*?[笑弧]", "嘴角笑意系列"),
                (r"(心中|内心)五味杂陈", "五味杂陈系列"),
                (r"如同.{1,10}一般", "如同一般系列"),
                (r"(眼神|目光|气势).{0,3}(变得|显得|愈发)?凌厉", "凌厉系列"),
                (r"(眼神|目光|眼中).{0,5}复杂", "复杂眼神系列"),
                (r"(内心|心中).{0,5}(泛起|涌起|掀起).{0,5}波澜", "心中波澜系列"),
                (r"(眼神|目光|眼眸).{0,3}(深邃|幽深)", "深邃眼神系列"),
                (r"(嘴角|脸上|眼中).{0,3}(浮现|闪过|掠过)一抹", "一抹系列"),
            ]
            self.compiled_patterns = [
                (re.compile(pattern), name, "warning", "", "")
                for pattern, name in legacy_patterns
            ]

    def scan_cliches(self, text: str) -> List[ClicheHit]:
        """扫描文本中的俗套句式

        Args:
            text: 要扫描的文本

        Returns:
            检测到的俗套句式列表，按出现位置排序
        """
        hits = []

        for item in self.compiled_patterns:
            if len(item) == 5:
                compiled_pattern, pattern_name, severity, category, hint = item
            else:
                compiled_pattern, pattern_name = item
                severity, category, hint = "warning", "", ""

            for match in compiled_pattern.finditer(text):
                hit = ClicheHit(
                    pattern=pattern_name,
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    severity=severity,
                    category=category,
                    replacement_hint=hint,
                )
                hits.append(hit)

        # 按位置排序
        hits.sort(key=lambda h: h.start)

        return hits

    def scan_by_category(self, text: str) -> Dict[str, List[ClicheHit]]:
        """按分类统计扫描结果"""
        hits = self.scan_cliches(text)
        by_category: Dict[str, List[ClicheHit]] = {}
        for h in hits:
            by_category.setdefault(h.category, []).append(h)
        return by_category

    def get_critical_count(self, text: str) -> int:
        """获取 critical 级别违规数"""
        return sum(1 for h in self.scan_cliches(text) if h.severity == "critical")

    def get_category_stats(self, text: str) -> Dict[str, int]:
        """获取分类统计"""
        hits = self.scan_cliches(text)
        stats: Dict[str, int] = {}
        for h in hits:
            stats[h.category] = stats.get(h.category, 0) + 1
        return stats
