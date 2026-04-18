"""V1 体量档位（T 恤尺码）：用户只选篇幅档，章数/每章字数/宏观结构由服务端推导并写入梗概黑盒。"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

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
        wpc = max(500, min(10000, wpc))
        total = int(meta["approx_total_words"])
        chapters = max(1, math.ceil(total / wpc))
        return chapters, wpc, tier

    tc = target_chapters if target_chapters and target_chapters > 0 else 100
    tw = target_words_per_chapter if target_words_per_chapter and target_words_per_chapter > 0 else 2500
    tw = max(500, min(10000, tw))
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
骨架：采用网文常用「起—承—转—合」节奏在章内落地；长篇层面用「英雄之旅」式推进（寻常世界→试炼→危机→蜕变→归来），具体情节仍须服从梗概与类型。
写作约束：避免用空话凑字；每章应完成可指认的情节推进或人物关系变化，环境/对白需服务于冲突与信息增量。"""
