"""Character naming seeds for Bible character generation.

The onboarding UI should not own name randomization.  This module gives the
generation prompt a small, pre-shuffled surname seed, then lets the model build
given names that match each role.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Iterable, Sequence


CLICHE_SURNAMES: frozenset[str] = frozenset({"李", "王", "张", "刘", "陈", "杨", "林", "赵", "周", "吴"})

COMPOUND_SURNAMES: tuple[str, ...] = (
    "欧阳", "司马", "上官", "诸葛", "慕容", "司徒", "司空", "尉迟", "公孙", "东方",
    "西门", "南宫", "皇甫", "令狐", "宇文", "长孙", "独孤", "端木", "濮阳", "轩辕",
    "即墨", "闻人", "申屠", "太叔", "呼延", "钟离", "澹台", "公冶", "宗政", "完颜",
    "耶律", "拓跋", "左丘", "谷梁", "乐正",
)

SINGLE_SURNAMES: tuple[str, ...] = (
    "顾", "苏", "沈", "萧", "裴", "荀", "喻", "柏", "水", "窦", "云", "狄", "贝", "明",
    "臧", "计", "伏", "茅", "庞", "纪", "舒", "屈", "祝", "阮", "蓝", "闵", "季", "路",
    "娄", "危", "童", "颜", "尹", "邵", "邹", "郝", "崔", "龚", "黎", "易", "武", "戴",
    "莫", "孔", "白", "常", "康", "傅", "严", "魏", "陶", "姜", "范", "叶", "余", "潘",
    "段", "贺", "毛", "江", "史", "侯", "倪", "覃", "温", "芦", "俞", "安", "梅", "辛",
    "管", "左", "薄", "宁", "柯", "桂", "柴", "车", "房", "边", "吉", "饶", "刁", "瞿",
    "戚", "丘", "米", "池", "滕", "佟", "言", "蔺", "栾", "冷", "茹", "蒲", "楼", "仇",
    "迟", "艾", "鱼", "容", "向", "古", "慎", "戈", "荆", "燕", "尚", "雍", "浦", "步",
    "耿", "满", "弘", "匡", "文", "寇", "阙", "沃", "蔚", "越", "巩", "聂", "晁", "敖",
    "融", "简", "沙", "鞠", "丰", "巢", "相", "游", "竺", "权", "桓",
)


@dataclass(frozen=True)
class CharacterSurnameSeed:
    """A preselected surname deck for one character-generation run."""

    surnames: tuple[str, ...]
    blocked_surnames: tuple[str, ...]

    def to_prompt_block(self) -> str:
        return (
            "【命名种子】\n"
            f"- 禁用姓氏：{'、'.join(self.blocked_surnames)}。\n"
            f"- 本次可用姓氏牌：{'、'.join(self.surnames)}。\n"
            "- 角色姓名必须优先使用上面的姓氏牌；主要角色尽量一人一姓，不要按列表顺序机械分配。\n"
            "- 只生成全名，不要在 JSON 中暴露姓氏牌、抽取过程或命名说明。\n"
            "- 名字由你根据角色阶层、地域、声线和时代感生成；避免网文高频套名。"
        )


def _stable_seed(value: str | None) -> int | None:
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def build_character_surname_seed(
    count: int,
    rng_seed: str | None = None,
    *,
    compound_ratio: float = 0.35,
    extra_surnames: Iterable[str] | None = None,
) -> CharacterSurnameSeed:
    """Build a shuffled surname seed for a character cast.

    Args:
        count: Number of surname cards requested.
        rng_seed: Optional stable seed source. Same seed and count yield the
            same surname deck.
        compound_ratio: Approximate ratio of compound surnames in the deck.
        extra_surnames: Optional domain-specific surnames injected by a caller.
    """
    requested = max(1, count)
    rng = random.Random(_stable_seed(rng_seed))

    extras = tuple(
        s.strip()
        for s in (extra_surnames or ())
        if s and s.strip() and s.strip() not in CLICHE_SURNAMES
    )
    compounds = list(dict.fromkeys((*extras, *COMPOUND_SURNAMES)))
    singles = list(dict.fromkeys(SINGLE_SURNAMES))
    rng.shuffle(compounds)
    rng.shuffle(singles)

    compound_count = min(len(compounds), max(1, round(requested * compound_ratio)))
    single_count = max(0, requested - compound_count)
    selected = compounds[:compound_count] + singles[:single_count]

    if len(selected) < requested:
        remainder = [s for s in compounds[compound_count:] + singles[single_count:] if s not in selected]
        selected.extend(remainder[: requested - len(selected)])

    rng.shuffle(selected)
    return CharacterSurnameSeed(
        surnames=tuple(selected[:requested]),
        blocked_surnames=tuple(sorted(CLICHE_SURNAMES)),
    )


def infer_surname(name: str, compound_surnames: Sequence[str] = COMPOUND_SURNAMES) -> str:
    """Infer surname from a Chinese full name for guardrails and dedupe."""
    stripped = (name or "").strip()
    if not stripped:
        return ""
    for surname in compound_surnames:
        if stripped.startswith(surname):
            return surname
    return stripped[:1]
