"""命名守门人 — 俗套检测与时代适配

检测维度：
1. 俗套姓氏检测：李、王、张、刘过度使用
2. 时代背景适配：古风名vs现代名
3. 复姓推荐库：诸葛、司马、慕容、东方等
4. 同音/谐音冲突检测

设计理念：
- 网文读者对名字敏感度极高
- "李天"、"王刚"这种名字让读者瞬间出戏
- 好名字 = 好印象 = 读者留存率
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class NamingViolation:
    """命名违规"""
    violation_type: str    # cliche_surname / era_mismatch / missing_compound_surname
    severity: float
    character_name: str
    suggestion: str

    @property
    def type_name(self) -> str:
        names = {
            "cliche_surname": "俗套姓氏",
            "era_mismatch": "时代背景不匹配",
            "missing_compound_surname": "建议使用复姓",
        }
        return names.get(self.violation_type, self.violation_type)


class NamingGuardrail:
    """命名守门人"""

    # 过度使用的姓氏（网文俗套）
    CLICHE_SURNAMES = {"李", "王", "张", "刘", "陈", "杨", "林", "赵", "周", "吴"}

    # 复姓库（适合武侠/仙侠/玄幻）
    COMPOUND_SURNAMES = [
        "诸葛", "司马", "慕容", "东方", "独孤", "令狐", "轩辕", "上官",
        "欧阳", "南宫", "皇甫", "公孙", "西门", "端木", "赫连", "尉迟",
    ]

    # 古风名字用字
    ANCIENT_NAME_CHARS = {
        "男": ["渊", "逸", "轩", "霖", "昊", "墨", "辰", "煜", "凌", "尘",
               "铮", "厉", "奕", "恒", "骞", "珏", "铮", "熙", "澈", "珩"],
        "女": ["婉", "清", "若", "霜", "芸", "璃", "萱", "澜", "霜", "霓",
               "绮", "芷", "莲", "琴", "蝶", "蓉", "芙", "月", "雪", "灵"],
    }

    # 现代名字用字（不适合古风）
    MODERN_NAME_CHARS = {"伟", "强", "刚", "磊", "鑫", "浩", "洋", "帅", "敏", "静",
                          "建", "国", "军", "华", "明", "志", "文", "平", "民", "勇"}

    def check(
        self,
        character_names: List[str],
        era: str = "ancient",
    ) -> Tuple[float, List[NamingViolation]]:
        """检查命名质量

        Args:
            character_names: 角色名列表
            era: 时代背景 (ancient/modern/mixed)

        Returns:
            (score, violations)
        """
        violations: List[NamingViolation] = []

        for name in character_names:
            if not name or len(name) < 1:
                continue

            # 1. 俗套姓氏检测
            violations.extend(self._check_cliche_surname(name))

            # 2. 时代背景适配
            if era in ("ancient", "mixed"):
                violations.extend(self._check_era_mismatch(name, era))

            # 3. 复姓推荐
            if era == "ancient":
                violations.extend(self._check_compound_surname(name))

        if not violations:
            return 1.0, []

        total_penalty = sum(v.severity for v in violations)
        score = max(0.0, 1.0 - total_penalty * 0.1)

        return score, violations

    def _check_cliche_surname(self, name: str) -> List[NamingViolation]:
        """俗套姓氏检测"""
        violations = []

        if len(name) >= 1 and name[0] in self.CLICHE_SURNAMES:
            violations.append(NamingViolation(
                violation_type="cliche_surname",
                severity=0.3,
                character_name=name,
                suggestion=f"姓氏'{name[0]}'过于常见，考虑使用更有个性的姓氏",
            ))

        return violations

    def _check_era_mismatch(self, name: str, era: str) -> List[NamingViolation]:
        """时代背景适配检测"""
        violations = []

        for char in name:
            if char in self.MODERN_NAME_CHARS:
                violations.append(NamingViolation(
                    violation_type="era_mismatch",
                    severity=0.5,
                    character_name=name,
                    suggestion=f"名字中的'{char}'偏现代感，与古风背景不太匹配",
                ))
                break  # 只报一次

        return violations

    def _check_compound_surname(self, name: str) -> List[NamingViolation]:
        """复姓推荐"""
        violations = []

        # 如果是单姓且名字只有2个字，建议使用复姓
        is_compound = any(name.startswith(cs) for cs in self.COMPOUND_SURNAMES)

        if not is_compound and len(name) == 2:
            # 名字太短，建议复姓增加辨识度
            suggestions = [cs for cs in self.COMPOUND_SURNAMES[:3]]
            violations.append(NamingViolation(
                violation_type="missing_compound_surname",
                severity=0.2,
                character_name=name,
                suggestion=f"两字名辨识度较低，可考虑复姓如{'、'.join(suggestions)}+名",
            ))

        return violations

    def suggest_name(self, era: str = "ancient", gender: str = "男") -> List[str]:
        """生成命名建议"""
        import random

        names = []
        for _ in range(5):
            if era == "ancient" and random.random() > 0.6:
                surname = random.choice(self.COMPOUND_SURNAMES)
                given = random.choice(self.ANCIENT_NAME_CHARS.get(gender, self.ANCIENT_NAME_CHARS["男"]))
                names.append(surname + given)
            else:
                # 单姓（避开俗套）
                rare_surnames = ["苏", "沈", "顾", "陆", "裴", "秦", "萧", "楚", "江", "谢"]
                surname = random.choice(rare_surnames)
                if era == "ancient":
                    given = random.choice(self.ANCIENT_NAME_CHARS.get(gender, self.ANCIENT_NAME_CHARS["男"]))
                else:
                    given = random.choice(["晨", "悦", "霖", "然", "轩"])
                names.append(surname + given)

        return names
