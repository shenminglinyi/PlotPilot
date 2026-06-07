"""V1 体量档位（T 恤尺码）：用户只选篇幅档，章数/每章字数/宏观结构由服务端推导并写入梗概黑盒。"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from application.core.chapter_target_limits import clamp_chapter_target_words

# 档位 id → 约总字数（规划目标，非公证成稿字数）
V1_LENGTH_TIERS: Dict[str, Dict[str, Any]] = {
    "short": {
        "label_zh": "短篇快穿 / 脑洞文",
        "approx_total_words": 300_000,
        "default_chapter_words": 2000,
    },
    "standard": {
        "label_zh": "标准商业连载",
        "approx_total_words": 1_000_000,
        "default_chapter_words": 2000,
    },
    "epic": {
        "label_zh": "宏大史诗巨著",
        "approx_total_words": 3_000_000,
        "default_chapter_words": 2000,
    },
}


def resolve_v1_length_params(
    length_tier: Optional[str],
    target_chapters: int,
    target_words_per_chapter: Optional[int],
) -> Tuple[int, int, Optional[str]]:
    """解析建档时的目标章数与每章字数。

    - 若提供合法 ``length_tier``：按档位推导章数（ceil(总字数/每章字)），每章字数取请求值或档位默认。
    - 否则：沿用 ``target_chapters``（默认至少 1）与 ``target_words_per_chapter``（默认 2500）。

    Returns:
        (target_chapters, target_words_per_chapter, normalized_tier_or_none)
    """
    tier = (length_tier or "").strip().lower()
    if tier in V1_LENGTH_TIERS:
        meta = V1_LENGTH_TIERS[tier]
        wpc = target_words_per_chapter if target_words_per_chapter and target_words_per_chapter > 0 else int(
            meta["default_chapter_words"]
        )
        wpc = clamp_chapter_target_words(wpc)
        total = int(meta["approx_total_words"])
        chapters = max(1, math.ceil(total / wpc))
        return chapters, wpc, tier

    tc = target_chapters if target_chapters and target_chapters > 0 else 100
    tw = target_words_per_chapter if target_words_per_chapter and target_words_per_chapter > 0 else 2500
    tw = clamp_chapter_target_words(tw)
    return tc, tw, None


def build_v1_structure_black_box_hint(
    tier_key: Optional[str],
    target_chapters: int,
    words_per_chapter: int,
) -> str:
    """写入梗概前缀的黑盒说明：供 Bible/规划/生成链路消费，界面不单独展示。"""
    approx_book = target_chapters * words_per_chapter
    # 卷数：最多 5 卷，按约每卷 100 章切分（与「商业五卷」叙事习惯对齐，仅为节奏提示）
    vol_cap = 5
    vols = min(vol_cap, max(1, (target_chapters + 99) // 100))
    ch_per_vol = max(1, math.ceil(target_chapters / vols))
    tier_label = ""
    if tier_key and tier_key in V1_LENGTH_TIERS:
        tier_label = f"（体量档：{V1_LENGTH_TIERS[tier_key]['label_zh']}）"

    return f"""【系统内部·叙事结构规划{tier_label}（勿向读者展示本段标题与标签）】
规划目标体量：约 {approx_book:,} 字；目标分章约 {target_chapters} 章；每章写作目标约 {words_per_chapter} 字。
宏观节奏：建议按约 {vols} 卷推进，每卷大致 {ch_per_vol} 章量级；每卷宜安排 2～3 个大高潮节点（幕级转折），卷末留强钩子。
骨架：采用「目标—阻力—转折—结果」的动态节奏在章内落地；长篇层面按作者梗概、题材赛道和世界规则自然推进，不预设固定神话旅程。
写作约束：避免用空话凑字；每章应完成可指认的情节推进或人物关系变化，环境/对白需服务于冲突与信息增量。"""


def strip_generated_premise_prefixes(premise: str) -> str:
    """Remove server-generated prefixes from user premise text."""
    text = str(premise or "").strip()
    if "【系统内部·叙事结构规划" in text:
        idx = text.find("\n\n")
        if idx != -1:
            text = text[idx + 2 :].strip()
    if text.startswith("【") and ("类型：" in text[:120] or "世界观基调：" in text[:120]):
        idx = text.find("\n\n")
        if idx != -1:
            text = text[idx + 2 :].strip()
    return text


def strip_v1_structure_black_box_hint(premise: str) -> str:
    """Backward-compatible alias for callers that clean generated premise text."""
    return strip_generated_premise_prefixes(premise)
