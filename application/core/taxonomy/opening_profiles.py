"""类型开篇画像加载与解析。

本模块只读取 `shared/taxonomy/opening_pattern_profiles_cn_v1.yaml` 中的配置资产，
不在代码里维护具体题材套路。调用方拿到的是可审计的 Variable Hub 变量块。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


DEFAULT_OPENING_PROFILE_BUNDLE_ID = "opening_pattern_profiles_cn_v1"


class OpeningProfileError(ValueError):
    """开篇画像解析失败。"""


@dataclass(frozen=True)
class GenreOpeningProfile:
    """Variable Hub 可消费的类型开篇画像。"""

    genre_major: str
    genre_theme: str
    source_level: str
    opening_profile: Mapping[str, Any]
    reader_contract: Mapping[str, Any]
    rhythm_constraints: Mapping[str, Any]

    def as_variables(self) -> dict[str, Any]:
        """返回稳定变量别名。"""
        return {
            "genre_opening_profile": dict(self.opening_profile),
            "genre_reader_contract": dict(self.reader_contract),
            "genre_rhythm_constraints": dict(self.rhythm_constraints),
        }


def opening_profile_yaml_path(bundle_id: str = DEFAULT_OPENING_PROFILE_BUNDLE_ID) -> Path:
    """返回 shared/taxonomy 下的开篇画像配置路径。"""
    here = Path(__file__).resolve()
    root = here.parents[3]
    return root / "shared" / "taxonomy" / f"{bundle_id}.yaml"


def load_opening_profile_bundle_dict(bundle_id: str = DEFAULT_OPENING_PROFILE_BUNDLE_ID) -> dict[str, Any]:
    """加载开篇画像配置。"""
    path = opening_profile_yaml_path(bundle_id)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise OpeningProfileError(f"开篇画像配置格式错误: {path}")
    return data


@lru_cache(maxsize=4)
def get_opening_profile_bundle_cached(bundle_id: str = DEFAULT_OPENING_PROFILE_BUNDLE_ID) -> dict[str, Any]:
    return load_opening_profile_bundle_dict(bundle_id)


def split_genre_label(genre_label: str) -> tuple[str, str]:
    """兼容前端/外部输入中的一级、二级分类分隔符。"""
    text = str(genre_label or "").strip()
    if not text:
        return "", ""
    for sep in ("/", "／", "-", "—", ">", "→"):
        if sep in text:
            parts = [part.strip() for part in text.split(sep) if part.strip()]
            if not parts:
                return "", ""
            if len(parts) == 1:
                return parts[0], ""
            return parts[0], " / ".join(parts[1:])
    return text, ""


def _profile_parts(raw: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    reader_promise = list(raw.get("reader_promise") or [])
    opening_mechanism = dict(raw.get("opening_mechanism") or {})
    rhythm_constraints = dict(raw.get("rhythm_constraints") or {})
    metric_snapshot = dict(raw.get("metric_snapshot") or {})
    opening_profile = {
        "reader_promise": reader_promise,
        "opening_mechanism": opening_mechanism,
        "metric_snapshot": metric_snapshot,
    }
    reader_contract = {
        "first_screen_hook": "第一屏必须让读者看到主角处境、异常点或待解决问题。",
        "chapter_1_payoff": "第一章必须兑现一个与分类承诺一致的收益、反转或追问。",
        "chapter_3_lock": "前三章需要锁定主线问题、能力机制或关系张力。",
        "chapter_10_loop": "十章内形成可重复的期待循环。",
        "reader_promise": reader_promise,
    }
    return opening_profile, reader_contract, rhythm_constraints


def resolve_opening_profile(
    genre_label: str,
    *,
    bundle: Mapping[str, Any] | None = None,
    strict: bool = True,
) -> GenreOpeningProfile | None:
    """按类型标签解析开篇画像。

    解析顺序：
    1. `一级 / 二级` 精确匹配；
    2. 只传二级时，在所有二级分类中唯一匹配；
    3. 同一一级分类的 `primary_defaults`。

    未命中时不拼硬编码提示词；`strict=True` 会直接阻塞调用方。
    """
    major, theme = split_genre_label(genre_label)
    data = dict(bundle or get_opening_profile_bundle_cached())
    profiles = data.get("profiles") or {}
    primary_defaults = data.get("primary_defaults") or {}
    primary_aliases = data.get("primary_aliases") or {}
    if isinstance(primary_aliases, Mapping) and major in primary_aliases:
        major = str(primary_aliases.get(major) or major)

    raw: Mapping[str, Any] | None = None
    source_level = ""
    if major and theme:
        raw = ((profiles.get(major) or {}).get(theme) if isinstance(profiles.get(major), Mapping) else None)
        source_level = "secondary"
    if raw is None and major and not theme:
        matches: list[tuple[str, Mapping[str, Any]]] = []
        for candidate_major, secondaries in profiles.items():
            if not isinstance(secondaries, Mapping):
                continue
            candidate = secondaries.get(major)
            if isinstance(candidate, Mapping):
                matches.append((str(candidate_major), candidate))
        if len(matches) == 1:
            major, theme = matches[0][0], major
            raw = matches[0][1]
            source_level = "secondary_alias"
    if raw is None and major:
        candidate = primary_defaults.get(major)
        if isinstance(candidate, Mapping):
            raw = candidate
            source_level = "primary_default"

    if raw is None:
        if strict:
            raise OpeningProfileError(f"类型开篇画像缺失，已阻塞生成: {genre_label or '(空)'}")
        return None

    opening_profile, reader_contract, rhythm_constraints = _profile_parts(raw)
    opening_profile.update(
        {
            "genre_major": major,
            "genre_theme": theme,
            "source_level": source_level,
        }
    )
    return GenreOpeningProfile(
        genre_major=major,
        genre_theme=theme,
        source_level=source_level,
        opening_profile=opening_profile,
        reader_contract=reader_contract,
        rhythm_constraints=rhythm_constraints,
    )
