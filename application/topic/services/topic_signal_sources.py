"""市场信号来源配置。"""
from __future__ import annotations

from application.topic.dtos import TopicMarketSignalSourceDTO


MARKET_SIGNAL_SOURCES = {
    "qidian_rank": TopicMarketSignalSourceDTO(
        key="qidian_rank",
        name="起点-小说榜",
        url="https://m.qidian.com/rank",
        category="novel",
        source_type="public_page",
        requires_auth=False,
    ),
    "jjwxc_rank": TopicMarketSignalSourceDTO(
        key="jjwxc_rank",
        name="晋江-小说榜",
        url="https://m.jjwxc.net/rank",
        category="novel",
        source_type="public_page",
        requires_auth=False,
    ),
    "qimao_rank": TopicMarketSignalSourceDTO(
        key="qimao_rank",
        name="七猫-小说榜",
        url="https://www.qimao.com/paihang",
        category="novel",
        source_type="public_page",
        requires_auth=False,
    ),
    "fanqie_rank": TopicMarketSignalSourceDTO(
        key="fanqie_rank",
        name="番茄-小说榜",
        url="https://fanqienovel.com/rank",
        category="novel",
        source_type="public_page",
        requires_auth=False,
    ),
    "qq_read": TopicMarketSignalSourceDTO(
        key="qq_read",
        name="腾讯-QQ阅读",
        url="https://ubook.reader.qq.com/api/book/rank?columnId=535193&pageIndex=1&pageSize=20",
        category="novel",
        source_type="api",
        requires_auth=False,
    ),
    "tencent_comic_rank": TopicMarketSignalSourceDTO(
        key="tencent_comic_rank",
        name="腾讯动漫-漫画榜",
        url="https://ac.qq.com/Rank/comicRank/type/pgv",
        category="comic",
        source_type="public_page",
        requires_auth=False,
    ),
    "kuaikan_comic": TopicMarketSignalSourceDTO(
        key="kuaikan_comic",
        name="快看漫画-漫画",
        url="https://www.kuaikanmanhua.com/ranking/",
        category="comic",
        source_type="public_page",
        requires_auth=False,
    ),
}

DEFAULT_MARKET_SIGNAL_SOURCE_WEIGHTS = {
    "qidian_rank": 1.0,
    "jjwxc_rank": 1.1,
    "qimao_rank": 0.95,
    "fanqie_rank": 1.05,
    "qq_read": 0.9,
    "tencent_comic_rank": 0.85,
    "kuaikan_comic": 0.7,
}
