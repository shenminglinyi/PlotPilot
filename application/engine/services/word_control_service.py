"""章节生成字数控制服务。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.ai.value_objects.prompt import Prompt


DEFAULT_TOLERANCE = 0.15
DEFAULT_MAX_EXPANSION_ATTEMPTS = 2
DEFAULT_MIN_TARGET = 500
DEFAULT_MAX_TARGET = 10000
TRIM_SEARCH_LOWER_BOUND = 0.9
TRIM_SENTENCE_ENDINGS = ("。", "！", "？", "」", "』", "”")


def effective_length(text: str) -> int:
    """按规格计算文本长度：直接用 len()，但忽略空白字符。"""
    return len("".join((text or "").split()))


@dataclass(frozen=True)
class WordCountCheckResult:
    target: int
    actual: int
    tolerance: float
    min_allowed: int
    max_allowed: int
    delta: int
    status: str

    @property
    def within_tolerance(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class WordControlMetadata:
    target: int
    actual: int
    tolerance: float
    delta: int
    status: str
    within_tolerance: bool
    action: str
    expansion_attempts: int
    trim_applied: bool
    fallback_used: bool
    min_allowed: int
    max_allowed: int


class WordControlService:
    """字数控制规则集合。"""

    def __init__(
        self,
        tolerance: float = DEFAULT_TOLERANCE,
        max_expansion_attempts: int = DEFAULT_MAX_EXPANSION_ATTEMPTS,
        min_target: int = DEFAULT_MIN_TARGET,
        max_target: int = DEFAULT_MAX_TARGET,
    ) -> None:
        if tolerance <= 0 or tolerance >= 1:
            raise ValueError("tolerance must be between 0 and 1")
        if max_expansion_attempts < 0:
            raise ValueError("max_expansion_attempts must be non-negative")
        self.tolerance = tolerance
        self.max_expansion_attempts = max_expansion_attempts
        self.min_target = min_target
        self.max_target = max_target

    def validate_target(self, target: int) -> None:
        if target <= 0:
            raise ValueError("target_word_count must be positive")

    def target_requires_warning(self, target: int) -> bool:
        self.validate_target(target)
        return target < self.min_target or target > self.max_target

    def check_word_count(
        self,
        text: str,
        target: int,
        tolerance: Optional[float] = None,
    ) -> WordCountCheckResult:
        self.validate_target(target)
        actual = effective_length(text)
        tol = self.tolerance if tolerance is None else tolerance
        min_allowed = max(1, int(target * (1 - tol)))
        max_allowed = max(min_allowed, int(target * (1 + tol)))

        if actual < min_allowed:
            status = "too_short"
        elif actual > max_allowed:
            status = "too_long"
        else:
            status = "ok"

        return WordCountCheckResult(
            target=target,
            actual=actual,
            tolerance=tol,
            min_allowed=min_allowed,
            max_allowed=max_allowed,
            delta=actual - target,
            status=status,
        )

    def inject_length_requirements(
        self,
        prompt: Prompt,
        *,
        target: int,
        tolerance: Optional[float] = None,
    ) -> Prompt:
        check = self.check_word_count("", target, tolerance=tolerance)
        guidance = (
            "\n【字数控制要求】\n"
            f"- 本章目标字数：{target} 字\n"
            f"- 允许范围：{check.min_allowed}-{check.max_allowed} 字（±{int(check.tolerance * 100)}%）\n"
            "- 必须在目标附近自然收束，不要为了凑字数重复情节或解释。\n"
            "- 不要输出章节标题、字数说明、后记。\n"
        )
        return Prompt(system=prompt.system + guidance, user=prompt.user)

    def build_expansion_prompt(
        self,
        *,
        existing_text: str,
        outline: str,
        target: int,
        current: int,
        attempt: int,
        max_attempts: int,
    ) -> Prompt:
        remaining = max(target - current, 0)
        system = (
            "你是长篇小说续写助手。你的任务是在不重复已有内容的前提下，为当前章节补写缺失部分。"
            "必须严格承接既有剧情、人物关系和叙事口吻，只输出可直接拼接到正文末尾的新内容。"
        )
        user = (
            f"章节目标字数：{target} 字\n"
            f"当前字数：{current} 字\n"
            f"建议补写：约 {remaining} 字\n"
            f"补写轮次：第 {attempt}/{max_attempts} 轮\n\n"
            f"章节大纲：\n{outline.strip()}\n\n"
            "已有章节内容如下，请从末尾自然续写：\n"
            f"{existing_text.strip()}\n\n"
            "硬性要求：\n"
            "- 严禁重复前文已出现的句子、动作、对白或总结。\n"
            "- 只补足缺失剧情，不重写开头。\n"
            "- 保持结尾自然，尽量朝目标字数靠拢。\n"
            "- 直接输出续写正文，不要解释。"
        )
        return Prompt(system=system, user=user)

    def trim_to_target(self, text: str, target: int) -> str:
        self.validate_target(target)
        stripped = (text or "").strip()
        if not stripped:
            return stripped

        if effective_length(stripped) <= target:
            return stripped

        lower_bound = max(1, int(target * TRIM_SEARCH_LOWER_BOUND))
        candidate_index = None
        for idx, _ in enumerate(stripped):
            current_len = effective_length(stripped[: idx + 1])
            if current_len < lower_bound:
                continue
            if current_len > target:
                break
            if stripped[idx] in TRIM_SENTENCE_ENDINGS:
                candidate_index = idx + 1

        if candidate_index is not None:
            return stripped[:candidate_index].rstrip()

        return self._trim_by_visible_chars(stripped, target)

    def _trim_by_visible_chars(self, text: str, target: int) -> str:
        pieces: list[str] = []
        visible = 0
        for char in text:
            if not char.isspace():
                visible += 1
            if visible > target:
                break
            pieces.append(char)
        return "".join(pieces).rstrip()
