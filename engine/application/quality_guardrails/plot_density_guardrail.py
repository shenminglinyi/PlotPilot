"""情节密度守门人 — 检测无营养的文字

三大检测维度：
1. 形容词功能性检查：每个形容词是否推进了叙事？
2. 段落目标推进检查：每段是否至少推进了一个叙事目标？
3. 信息密度阈值：每千字的有效信息量

示例：
- 无功能形容词 ❌："寒冷的冰冷的刺骨的寒风吹过"
- 有效形容词 ✅："寒风裹着碎雪灌进领口"（寒风+碎雪+灌=三个信息点）

- 无效段落 ❌：纯粹描写风景，不推进任何目标
- 有效段落 ✅：风景描写暗含危险信号（推进紧张感目标）
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class DensityViolation:
    """密度违规"""
    violation_type: str    # non_functional_adj / no_goal_progression / low_info_density
    severity: float
    description: str
    suggestion: str
    position: str = ""


class PlotDensityGuardrail:
    """情节密度守门人"""

    # 信息密度阈值（有效信息点/千字）
    MIN_INFO_DENSITY = 5  # 每千字至少5个信息点

    # 形容词堆叠模式
    ADJ_STACK_PATTERNS = [
        r'((?:的[\u4e00-\u9fff]{1,3}){3,})',  # 连续3+个"的X"结构
        r'((?:[\u4e00-\u9fff]{1,3}的){3,})',   # 连续3+个"X的"结构
        r'((?:[\u4e00-\u9fff]{1,3}){4,}地)',     # 连续4+个副词修饰
    ]

    # 常见无功能修饰词
    FILLER_PHRASES = [
        "不由得", "忍不住", "情不自禁", "下意识地",
        "默默地", "轻轻地", "缓缓地", "微微地",
        "似乎", "仿佛", "好像", "大概",
        "非常", "十分", "极其", "格外", "特别",
    ]

    # 纯描写/无叙事推进的关键信号（纯风景描写的典型用词）
    PURE_DESCRIPTION_SIGNALS = [
        # 纯风景描写
        "群山连绵", "白云悠悠", "蜿蜒穿过", "青翠的草地",
        "露珠折射", "鸟儿歌唱", "蝴蝶起舞", "花间起舞",
        "宁静祥和", "心旷神怡", "流连忘返",
        "阳光洒在", "枝头歌唱",
        # 纯情感描写（无事件推进）
        "让人心旷神怡", "世间一切烦恼", "仿佛都消散",
        "莫名的情绪", "不可阻挡", "无法回去",
        "十字路口", "不知道该",
        # 过度写景的句式标记
        "远处", "一片.*?景象",
    ]

    # 纯情感独白信号（无事件推进，只有内心感受）
    PURE_EMOTION_SIGNALS = [
        "莫名的情绪", "涌起一股", "如同潮水般", "理智.*?淹没",
        "快乐与悲伤", "再也见不到", "不知道该选",
        "无法回去", "像是站在",
    ]

    # 叙事推进关键词（只要包含这些，就有推进）
    NARRATIVE_PROGRESSION_WORDS = [
        # 动作类（真正的动作，不只是描写）
        "推", "走", "跑", "抓", "握", "拔", "刺", "砍", "打", "踢",
        "发现", "看到", "意识到", "明白", "知道", "听到",
        "说", "喊", "叫", "问",
        # 冲突类
        "却", "但", "然而", "可是", "偏偏", "居然", "竟然",
        "冲突", "对抗", "争吵", "对峙",
        # 事件类
        "出现", "消失", "变化", "转变", "爆发",
    ]

    def check(self, text: str, chapter_goal: str = "") -> Tuple[float, List[DensityViolation]]:
        """检查文本的情节密度

        Args:
            text: 待检查文本
            chapter_goal: 章节目标（用于检查推进）

        Returns:
            (score, violations)
        """
        violations: List[DensityViolation] = []

        # 1. 形容词功能性检查
        violations.extend(self._check_adjective_functionality(text))

        # 2. 段落目标推进检查
        violations.extend(self._check_paragraph_progression(text, chapter_goal))

        # 3. 信息密度阈值
        violations.extend(self._check_info_density(text))

        if not violations:
            return 1.0, []

        total_penalty = sum(v.severity for v in violations)
        score = max(0.0, 1.0 - total_penalty * 0.15)

        return score, violations

    def _check_adjective_functionality(self, text: str) -> List[DensityViolation]:
        """形容词功能性检查"""
        violations = []

        # 检测形容词堆叠
        for pattern in self.ADJ_STACK_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                violations.append(DensityViolation(
                    violation_type="non_functional_adj",
                    severity=0.5,
                    description=f"形容词堆叠：'{match.group()}'，大部分不推进叙事",
                    suggestion="只保留1个最有信息量的修饰，用动作/细节替代其他",
                    position=f"pos {match.start()}",
                ))

        # 检测填充词过多
        filler_count = sum(text.count(phrase) for phrase in self.FILLER_PHRASES)
        if filler_count > 5:
            violations.append(DensityViolation(
                violation_type="non_functional_adj",
                severity=0.4,
                description=f"填充词过多({filler_count}个)，降低信息密度",
                suggestion="减少'似乎、仿佛、轻轻地'等填充词，直接描写",
            ))

        return violations

    def _check_paragraph_progression(self, text: str, chapter_goal: str) -> List[DensityViolation]:
        """段落目标推进检查"""
        violations = []

        # 按换行分段，如果只有一段则整段分析
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text.strip()]

        for i, para in enumerate(paragraphs):
            if len(para) < 10:  # 过短的段落跳过
                continue

            # 方法1：基于正则的叙事推进检测
            has_action = bool(re.search(r'[\u4e00-\u9fff]{2,6}(了|着|过|起来|下去|出来)', para))
            has_dialogue = any(q in para for q in ['\u201c', '\u201d', '"', '\u300c'])
            has_discovery = bool(re.search(r'(发现|意识到|明白|知道|看到|听到)', para))
            has_conflict = bool(re.search(r'(却|但|然而|可是|偏偏|居然|竟然)', para))
            # has_transition 不算叙事推进，只是连接词

            has_progression = has_action or has_dialogue or has_discovery or has_conflict

            # 方法2：纯描写信号检测（检测纯风景/纯氛围描写）
            is_pure_description = self._detect_pure_description(para)

            # 如果段落较长且没有叙事推进，或者被判定为纯描写
            if (not has_progression and len(para) > 50) or (is_pure_description and len(para) > 50):
                violations.append(DensityViolation(
                    violation_type="no_goal_progression",
                    severity=0.6,
                    description=f"段落{i+1}({len(para)}字)没有推进叙事目标" +
                                ("，属于纯描写段落" if is_pure_description else ""),
                    suggestion="为纯描写段落添加叙事功能：暗含危险、折射心理、埋设伏笔",
                ))

        return violations

    def _detect_pure_description(self, para: str) -> bool:
        """检测是否为纯描写段落（无叙事功能）

        通过分析段落中的动词类型和描写类型来判断
        """
        # 统计纯描写信号的数量
        signal_count = 0
        for signal in self.PURE_DESCRIPTION_SIGNALS:
            if re.search(signal, para):
                signal_count += 1

        # 如果有3个以上的纯描写信号，很可能是纯描写
        if signal_count >= 3:
            return True

        # 检查动词密度：纯描写段落的动词多为感官动词和存在动词
        sensory_verbs = re.findall(r'(看|听|闻|感|觉|映|照|洒|飘|飞|流|唱|舞)', para)
        action_verbs = re.findall(r'(推|抓|握|拔|刺|砍|打|跑|冲|跳|喊|说|问|发现|冲出)', para)

        # 感官动词远多于动作动词 = 纯描写
        if len(sensory_verbs) > len(action_verbs) * 3 and len(sensory_verbs) >= 3:
            return True

        # 检查是否缺乏真正的叙事主体（角色）
        # 纯描写段落通常不包含具体角色的动作
        has_character_action = bool(re.search(r'[\u4e00-\u9fff]{2,4}(推|走|跑|抓|握|拔|刺|砍|打|说|喊|发现|转身|走出)', para))
        if not has_character_action and len(para) > 80 and signal_count >= 1:
            return True

        return False

    def _check_info_density(self, text: str) -> List[DensityViolation]:
        """信息密度阈值检查"""
        violations = []

        # 估算信息点数量
        word_count = len(text.replace(" ", "").replace("\n", ""))
        if word_count < 100:
            return violations

        # 信息点标记（粗略估算）
        info_points = 0

        # 动作 = 信息点
        info_points += len(re.findall(r'[\u4e00-\u9fff]{2,6}(了|着|过)', text))

        # 对话 = 信息点
        info_points += len(re.findall(r'[\u201c\u201d"\u300c]', text)) // 2

        # 发现/揭示 = 信息点
        info_points += len(re.findall(r'(发现|揭示|暴露|泄露|坦白|承认)', text))

        # 冲突 = 信息点
        info_points += len(re.findall(r'(冲突|对抗|争吵|对峙|翻脸)', text))

        # 计算信息密度
        density = info_points / (word_count / 1000) if word_count > 0 else 0

        if density < self.MIN_INFO_DENSITY:
            violations.append(DensityViolation(
                violation_type="low_info_density",
                severity=0.7,
                description=f"信息密度{density:.1f}点/千字，低于阈值{self.MIN_INFO_DENSITY}",
                suggestion="增加有效动作、对话和信息揭示，减少纯描写和填充",
            ))

        return violations

    def compute_density_score(self, text: str) -> float:
        """计算信息密度评分"""
        word_count = len(text.replace(" ", "").replace("\n", ""))
        if word_count < 50:
            return 1.0

        info_points = 0
        info_points += len(re.findall(r'[\u4e00-\u9fff]{2,6}(了|着|过)', text))
        info_points += len(re.findall(r'[\u201c\u201d"\u300c]', text)) // 2
        info_points += len(re.findall(r'(发现|揭示|坦白|承认)', text))
        info_points += len(re.findall(r'(冲突|对抗|对峙|翻脸)', text))

        density = info_points / (word_count / 1000) if word_count > 0 else 0
        # 归一化到0-1
        return min(1.0, density / (self.MIN_INFO_DENSITY * 2))
