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
        rank_urls={
            "热门榜": "https://m.qidian.com/rank/",
            "新书榜": "https://m.qidian.com/rank/newbook/",
            "快速上榜": "https://m.qidian.com/rank/sign/",
        },
    ),
    "jjwxc_rank": TopicMarketSignalSourceDTO(
        key="jjwxc_rank",
        name="晋江-小说榜",
        url="https://m.jjwxc.net/rank",
        category="novel",
        source_type="public_page",
        requires_auth=False,
        rank_urls={
            "热门榜": "https://m.jjwxc.net/rank/naturalmore/64",
            "新书榜": "https://m.jjwxc.net/rank/naturalmore/29",
            "快速上榜": "https://m.jjwxc.net/rank/naturalmore/36",
        },
    ),
    "qimao_rank": TopicMarketSignalSourceDTO(
        key="qimao_rank",
        name="七猫-小说榜",
        url="https://www.qimao.com/paihang",
        category="novel",
        source_type="public_page",
        requires_auth=False,
        rank_urls={
            "热门榜": "https://www.qimao.com/paihang/boy/hot/date/",
            "新书榜": "https://www.qimao.com/paihang/boy/new/date/",
            "快速上榜": "https://www.qimao.com/paihang/boy/leap/date/",
        },
    ),
    "fanqie_rank": TopicMarketSignalSourceDTO(
        key="fanqie_rank",
        name="番茄-小说榜",
        url="https://fanqienovel.com/rank",
        category="novel",
        source_type="public_page",
        requires_auth=False,
        rank_urls={
            "热门榜": "https://fanqienovel.com/rank/1_2_1141",
            "新书榜": "https://fanqienovel.com/rank/1_1_1141",
            "快速上榜": "https://fanqienovel.com/rank/1_2_1140",
        },
    ),
    "qq_read": TopicMarketSignalSourceDTO(
        key="qq_read",
        name="腾讯-QQ阅读",
        url="https://ubook.reader.qq.com/api/book/rank?columnId=535193&pageIndex=1&pageSize=20",
        category="novel",
        source_type="api",
        requires_auth=False,
        rank_urls={
            "热门榜": "https://ubook.reader.qq.com/api/book/rank?columnId=535193&pageIndex=1&pageSize=20",
            "新书榜": "https://ubook.reader.qq.com/api/book/rank?columnId=535194&pageIndex=1&pageSize=20",
            "快速上榜": "https://ubook.reader.qq.com/api/book/rank?columnId=535189&pageIndex=1&pageSize=20",
        },
    ),
    "tencent_comic_rank": TopicMarketSignalSourceDTO(
        key="tencent_comic_rank",
        name="腾讯动漫-漫画榜",
        url="https://ac.qq.com/Rank/comicRank/type/pgv",
        category="comic",
        source_type="public_page",
        requires_auth=False,
        rank_urls={
            "热门榜": "https://ac.qq.com/Rank/comicRank/type/pgv",
            "新书榜": "https://ac.qq.com/Rank/comicRank/type/new",
            "快速上榜": "https://ac.qq.com/Rank/comicRank/type/rise",
        },
    ),
    "kuaikan_comic": TopicMarketSignalSourceDTO(
        key="kuaikan_comic",
        name="快看漫画-漫画",
        url="https://www.kuaikanmanhua.com/ranking/",
        category="comic",
        source_type="public_page",
        requires_auth=False,
        rank_urls={
            "热门榜": "https://www.kuaikanmanhua.com/ranking/9",
            "新书榜": "https://www.kuaikanmanhua.com/ranking/2",
            "快速上榜": "https://www.kuaikanmanhua.com/ranking/7",
        },
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
