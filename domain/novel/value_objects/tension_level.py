from enum import Enum


class TensionLevel(int, Enum):
    """张力等级（1-10 档，对应 0-100 分的十分位）

    网文叙事的专业张力标尺：
    1 = 死水（纯日常/过渡，零冲突零悬念）
    2 = 微澜（有事件但无威胁，轻松解决）
    3 = 涟漪（小麻烦/小误会，不影响主线）
    4 = 暗流（真正阻碍出现，读者开始紧张）
    5 = 涌潮（核心危机浮现，信息差制造悬念）
    6 = 惊浪（多方博弈/重大选择，一步错满盘输）
    7 = 风暴（底牌揭晓/核心关系破裂/生死一线）
    8 = 狂澜（绝境/多方修罗场，不可逆转）
    9 = 巅峰（灵魂黑夜/极致燃/催泪级）
    10 = 极限（全书最高潮，所有矛盾终极爆发）

    向后兼容：LOW=1, MEDIUM=4, HIGH=7, PEAK=10 仍可使用
    """
    LOW = 1          # 死水
    RIPPLE = 2       # 微澜
    STIR = 3         # 涟漪
    MEDIUM = 4       # 暗流
    SURGE = 5        # 涌潮
    TENSION_6 = 6    # 惊浪
    HIGH = 7         # 风暴
    TENSION_8 = 8    # 狂澜
    TENSION_9 = 9    # 巅峰
    PEAK = 10        # 极限

    @classmethod
    def from_score(cls, score: float) -> "TensionLevel":
        """将 0-100 的张力分值映射到 TensionLevel（1-10）。

        使用非线性映射，让中间段更敏感：
        - 0-10  → 1 (LOW)
        - 11-20 → 2 (RIPPLE)
        - 21-35 → 3 (STIR)
        - 36-45 → 4 (MEDIUM)
        - 46-55 → 5 (SURGE)
        - 56-65 → 6 (TENSION_6)
        - 66-75 → 7 (HIGH)
        - 76-85 → 8 (TENSION_8)
        - 86-94 → 9 (TENSION_9)
        - 95-100 → 10 (PEAK)
        """
        if score <= 10:
            return cls.LOW
        elif score <= 20:
            return cls.RIPPLE
        elif score <= 35:
            return cls.STIR
        elif score <= 45:
            return cls.MEDIUM
        elif score <= 55:
            return cls.SURGE
        elif score <= 65:
            return cls.TENSION_6
        elif score <= 75:
            return cls.HIGH
        elif score <= 85:
            return cls.TENSION_8
        elif score <= 94:
            return cls.TENSION_9
        else:
            return cls.PEAK

    @property
    def display_name(self) -> str:
        """中文显示名"""
        names = {
            1: "死水", 2: "微澜", 3: "涟漪", 4: "暗流", 5: "涌潮",
            6: "惊浪", 7: "风暴", 8: "狂澜", 9: "巅峰", 10: "极限",
        }
        return names.get(self.value, "未知")
