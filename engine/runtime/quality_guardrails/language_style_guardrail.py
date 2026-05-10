"""语言风格守门人 — 去AI味检测

四大检测维度：
1. 八股文检测：模板化结构（首先...其次...最后...）
2. 数字比喻检测："像X一样Y"的过度使用
3. 过度理性检测：情绪场景中的理性分析
4. 拐弯描写检测：明明可以直接写，偏要绕三个弯

示例：
- 八股文 ❌："他的内心经历了三个阶段：首先是震惊，其次是愤怒，最后是释然。"
- 八股文 ✅："他愣了半晌，攥紧的拳头慢慢松开。"

- 数字比喻 ❌："她的笑容像春天的阳光一样温暖。"
- 数字比喻 ✅："她笑了，眼底有光。"

- 过度理性 ❌："面对母亲的离世，他开始分析自己在家庭中的角色定位..."
- 过度理性 ✅："他跪在那里，什么都想不起来。"

- 拐弯描写 ❌："他不由自主地在心中产生了一种无法言说的、仿佛被什么东西深深触动的感觉。"
- 拐弯描写 ✅："他心里一颤。"
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StyleViolation:
    """风格违规"""
    violation_type: str    # eight_legs / number_metaphor / over_rational / detour
    severity: float        # 0.0-1.0
    original_text: str
    suggestion: str
    line_number: int = 0

    @property
    def type_name(self) -> str:
        names = {
            "eight_legs": "八股文",
            "number_metaphor": "数字比喻",
            "over_rational": "过度理性",
            "detour": "拐弯描写",
        }
        return names.get(self.violation_type, self.violation_type)


class LanguageStyleGuardrail:
    """语言风格守门人

    检测AI写作的四大典型问题，提供替代方案建议
    """

    # 八股文模式
    EIGHT_LEGS_PATTERNS = [
        (r'首先.{0,10}其次.{0,10}最后', '八股文三段式'),
        (r'第一.{0,10}第二.{0,10}第三', '八股文三段式'),
        (r'先是.{0,10}随后.{0,10}(最终|最后|终于)', '八股文三段式(先是/随后/最终)'),
        (r'先是.{0,8}接着.{0,8}(然后|最后)', '八股文三段式(先是/接着/然后)'),
        (r'起初.{0,10}后来.{0,10}(最终|最后|终于)', '八股文三段式(起初/后来/最终)'),
        (r'一方面.{0,10}另一方面', '八股文两面式'),
        (r'不仅.*?而且.*?更', '八股文递进式'),
        (r'总体而言|综上所述|总而言之', '八股文总结式'),
        (r'从.{1,8}角度(来看|来说)', '八股文分析式'),
        (r'这体现了|这反映了|这表明了', '八股文解读式'),
    ]

    # 数字比喻模式
    NUMBER_METAPHOR_PATTERNS = [
        (r'像.{1,6}一样.{2,8}', '明喻（像X一样Y）'),
        (r'仿佛.{1,6}一般.{2,8}', '明喻（仿佛X一般Y）'),
        (r'犹如.{1,6}般', '明喻（犹如X般）'),
        (r'如同.{1,4}似.{1,4}', '明喻（如同X似Y）'),
    ]

    # 过度理性模式
    OVER_RATIONAL_PATTERNS = [
        (r'(分析|评估|判断|权衡|考量).{0,6}(自己的|对方的|当前的)', '情绪场景中的理性分析'),
        (r'(意识到|认识到|体会到).{0,10}(重要性|关键性|必要性)', '感悟式理性总结'),
        (r'(从.*?的角度|站在.*?立场).{0,10}(思考|审视|看待)', '视角式理性分析'),
        (r'(内心深处|心底).{0,10}(明白|清楚|知道).{0,10}(必须|应该|需要)', '内心独白式说教'),
        (r'(评估|分析|计算|衡量).{0,10}(投入|回报|成本|收益|风险)', '商业分析式理性'),
        (r'(开始|试图|试着).{0,6}(分析|评估|判断|权衡|考量).{0,15}(关系|感情|情感|局面)', '情绪场景中突然理性分析'),
    ]

    # 拐弯描写模式
    DETOUR_PATTERNS = [
        (r'不由自主地.{2,10}了一种.{2,10}的.{2,10}感觉', '感受拐弯描写'),
        (r'仿佛.{2,8}般地.{2,8}着.{2,8}的.{2,8}', '多重修饰拐弯'),
        (r'一种无法(言说|形容|描述|言喻).{0,10}的.{2,10}', '无法言说式拐弯'),
        (r'在.{2,6}(之中|之间|之内).{2,10}的.{2,10}', '嵌套结构拐弯'),
        (r'一种.{2,8}的.{2,8}的.{2,8}(感觉|感受|情绪|冲动)', '多重定语拐弯'),
        (r'(从|自).{2,8}(涌上|升起|产生|袭来).{0,8}(的|着).{0,8}(感觉|感受|冲动)', '来源式拐弯描写'),
    ]

    def check(self, text: str) -> Tuple[float, List[StyleViolation]]:
        """检查文本的语言风格

        Args:
            text: 待检查文本

        Returns:
            (score, violations) — 评分(0-1)和违规列表
        """
        violations: List[StyleViolation] = []

        # 1. 八股文检测
        violations.extend(self._check_eight_legs(text))

        # 2. 数字比喻检测
        violations.extend(self._check_number_metaphor(text))

        # 3. 过度理性检测
        violations.extend(self._check_over_rational(text))

        # 4. 拐弯描写检测
        violations.extend(self._check_detour(text))

        # 计算评分
        if not violations:
            return 1.0, []

        # 加权评分
        total_penalty = sum(v.severity for v in violations)
        score = max(0.0, 1.0 - total_penalty * 0.15)

        return score, violations

    def _check_eight_legs(self, text: str) -> List[StyleViolation]:
        """八股文检测"""
        violations = []
        for pattern, desc in self.EIGHT_LEGS_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                violations.append(StyleViolation(
                    violation_type="eight_legs",
                    severity=0.7,
                    original_text=match.group(),
                    suggestion=f"避免{desc}，改用具体的动作和细节来展现",
                ))
        return violations

    def _check_number_metaphor(self, text: str) -> List[StyleViolation]:
        """数字比喻检测"""
        violations = []
        count = 0
        for pattern, desc in self.NUMBER_METAPHOR_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                count += 1
                if count > 1:  # 允许1个，多了就报违规
                    violations.append(StyleViolation(
                        violation_type="number_metaphor",
                        severity=0.5,
                        original_text=match.group(),
                        suggestion="减少明喻使用，改用白描或暗喻",
                    ))
        return violations

    def _check_over_rational(self, text: str) -> List[StyleViolation]:
        """过度理性检测"""
        violations = []
        for pattern, desc in self.OVER_RATIONAL_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                violations.append(StyleViolation(
                    violation_type="over_rational",
                    severity=0.8,
                    original_text=match.group(),
                    suggestion=f"避免{desc}，情绪场景应用身体反应替代分析",
                ))
        return violations

    def _check_detour(self, text: str) -> List[StyleViolation]:
        """拐弯描写检测"""
        violations = []
        for pattern, desc in self.DETOUR_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                violations.append(StyleViolation(
                    violation_type="detour",
                    severity=0.6,
                    original_text=match.group(),
                    suggestion=f"简化表达，{desc}可以用1-2个词直接描写",
                ))
        return violations

    def generate_replacement(self, violation: StyleViolation) -> str:
        """生成替代方案建议

        根据违规类型提供不同的修改方向
        """
        strategies = {
            "eight_legs": "用动作和细节替代总结：不要'他经历了三个阶段'，而是描写具体的表情、动作变化",
            "number_metaphor": "用白描替代明喻：不要'像阳光一样温暖'，而是'她笑了，眼底有光'",
            "over_rational": "用身体反应替代分析：不要'他分析了局势'，而是'他的手不自觉地握紧了'",
            "detour": "直接写：不要'不由自主地产生了一种感觉'，而是'心里一颤'",
        }
        return strategies.get(violation.violation_type, "简化表达，去掉冗余修饰")
