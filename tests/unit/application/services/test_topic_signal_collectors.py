"""市场信号采集器测试。"""

from application.topic.dtos import (
    TopicMarketSignalDTO,
    TopicMarketSignalSourceCredentialDTO,
    TopicMarketSignalSourceDTO,
)
from application.topic.services.topic_signal_collectors import (
    build_market_signal_collectors,
    collect_market_signals_from_source,
)
from application.topic.services.topic_signal_sources import MARKET_SIGNAL_SOURCES


def test_collect_market_signals_from_public_page_source():
    html = """
    <html>
      <h2>债务修仙</h2><p>玄幻·升级</p>
      <h2>契约少女</h2><p>漫画·恋爱</p>
    </html>
    """
    source = TopicMarketSignalSourceDTO(
        key="qidian_rank",
        name="起点-小说榜",
        url="https://www.qidian.com/rank/",
        category="novel",
        source_type="public_page",
        requires_auth=False,
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert [item.title for item in signals] == ["债务修仙", "契约少女"]


def test_collect_public_page_source_fetches_rank_dimensions():
    html_by_url = {
        "https://example.com/hot": "<html><h2>热榜修仙</h2></html>",
        "https://example.com/new": "<html><h2>新书神探</h2></html>",
        "https://example.com/rising": "<html><h2>飙升赘婿</h2></html>",
    }
    fetched_urls = []

    def fetch_text(url):
        fetched_urls.append(url)
        return html_by_url[url]

    source = TopicMarketSignalSourceDTO(
        key="example_rank",
        name="示例榜",
        url="https://example.com/rank",
        category="novel",
        source_type="public_page",
        rank_urls={
            "热门榜": "https://example.com/hot",
            "新书榜": "https://example.com/new",
            "快速上榜": "https://example.com/rising",
        },
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=fetch_text,
        limit=1,
        collectors=build_market_signal_collectors(),
    )

    assert fetched_urls == [
        "https://example.com/hot",
        "https://example.com/new",
        "https://example.com/rising",
    ]
    assert [item.title for item in signals] == ["热榜修仙", "新书神探", "飙升赘婿"]
    assert signals[0].tags == ["热门榜"]
    assert "热门榜" in signals[0].summary
    assert signals[1].tags == ["新书榜"]
    assert "新书榜" in signals[1].summary
    assert signals[2].tags == ["快速上榜"]
    assert "快速上榜" in signals[2].summary


def test_collect_api_source_fetches_rank_dimensions():
    payload_by_url = {
        "https://api.example.com/hot": '{"books":[{"bookName":"热榜长生","categoryName":"仙侠"}]}',
        "https://api.example.com/new": '{"books":[{"bookName":"新书诡案","categoryName":"悬疑"}]}',
        "https://api.example.com/rising": '{"books":[{"bookName":"飙升豪门","categoryName":"现言"}]}',
    }
    fetched_urls = []

    def fetch_text(url, _headers=None):
        fetched_urls.append(url)
        return payload_by_url[url]

    source = TopicMarketSignalSourceDTO(
        key="example_api",
        name="示例 API 榜",
        url="https://api.example.com/rank",
        category="novel",
        source_type="api",
        rank_urls={
            "热门榜": "https://api.example.com/hot",
            "新书榜": "https://api.example.com/new",
            "快速上榜": "https://api.example.com/rising",
        },
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=fetch_text,
        limit=1,
        collectors=build_market_signal_collectors(),
        credentials=TopicMarketSignalSourceCredentialDTO(source_key="example_api", api_key="token"),
    )

    assert fetched_urls == [
        "https://api.example.com/hot",
        "https://api.example.com/new",
        "https://api.example.com/rising",
    ]
    assert [item.title for item in signals] == ["热榜长生", "新书诡案", "飙升豪门"]
    assert signals[0].tags == ["仙侠", "热门榜"]
    assert "热门榜" in signals[0].summary
    assert signals[1].tags == ["悬疑", "新书榜"]
    assert "新书榜" in signals[1].summary
    assert signals[2].tags == ["现言", "快速上榜"]
    assert "快速上榜" in signals[2].summary


def test_default_market_sources_cover_hot_new_and_rising_ranks():
    for source in MARKET_SIGNAL_SOURCES.values():
        assert {"热门榜", "新书榜", "快速上榜"}.issubset(source.rank_urls)


def test_collect_qidian_rank_extracts_book_metadata():
    html = """
    <div class="book-mid-info">
      <h2><a href="//book.qidian.com/info/1">没钱修什么仙？</a></h2>
      <p class="author">
        <a>熊狼狗</a><em>|</em><a>轻小说</a><em>|</em><a>原生幻想</a><em>|</em><span>连载</span>
      </p>
      <p class="intro">老者目光深邃，开局就是债务和修仙规则冲突。</p>
    </div>
    <div class="book-mid-info">
      <h2><a href="//book.qidian.com/info/2">苟在初圣魔门当人材</a></h2>
      <p class="author">
        <a>鹤守月满池</a><em>|</em><a>仙侠</a><em>|</em><a>幻想修仙</a><em>|</em><span>连载</span>
      </p>
      <p class="intro">魔门底层人材靠低风险选择积累优势。</p>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="qidian_rank",
        name="起点-小说榜",
        url="https://www.qidian.com/rank/",
        category="novel",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "没钱修什么仙？"
    assert signals[0].genre == "轻小说"
    assert signals[0].tags == ["轻小说", "原生幻想"]
    assert "债务和修仙规则冲突" in signals[0].summary
    assert signals[1].genre == "仙侠"


def test_collect_qidian_mobile_rank_extracts_book_metadata():
    html = """
    <div class="_rankTitle_17ayl_517"><span>月票榜</span></div>
    <a class="_bookWrapper_1g1ce_193 _bookItem_17ayl_586" href="//m.qidian.com/book/1035420986/">
      <div class="_ranking_17ayl_590">1</div>
      <h2 class="_title_17ayl_681">玄鉴仙族</h2>
      <p class="_subTitle_17ayl_725">季越人 <em>·</em> 仙侠 <em>·</em> 563.79万字</p>
    </a>
    <a class="_bookWrapper_1g1ce_193 _bookItem_17ayl_586" href="//m.qidian.com/book/1041637443/">
      <div class="_ranking_17ayl_590">2</div>
      <h2 class="_title_17ayl_681">捞尸人</h2>
      <p class="_subTitle_17ayl_725">纯洁滴小龙 <em>·</em> 悬疑 <em>·</em> 84.2万字</p>
    </a>
    """
    source = TopicMarketSignalSourceDTO(
        key="qidian_rank",
        name="起点-小说榜",
        url="https://m.qidian.com/rank",
        category="novel",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "玄鉴仙族"
    assert signals[0].genre == "仙侠"
    assert signals[0].tags == ["仙侠", "月票榜"]
    assert "月票榜第1名" in signals[0].summary
    assert signals[1].title == "捞尸人"


def test_collect_fanqie_rank_extracts_book_metadata():
    html = """
    <div class="muye-rank-book-item">
      <a href="/page/123"><div class="book-name">十日终焉</div></a>
      <div class="author">杀虫队队员</div>
      <div class="book-tags"><span>悬疑脑洞</span><span>都市脑洞</span><span>连载中</span></div>
      <div class="book-desc">当我以为这只是一次普通密室逃脱时，所有规则都开始反噬。</div>
    </div>
    <div class="muye-rank-book-item">
      <a href="/page/456"><div class="book-name">全民转职：开局觉醒隐藏职业</div></a>
      <div class="book-tags"><span>都市高武</span><span>系统</span></div>
      <div class="book-desc">全民觉醒职业，主角在低评分职业里找到隐藏进化路线。</div>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="fanqie_rank",
        name="番茄-小说榜",
        url="https://fanqienovel.com/rank",
        category="novel",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "十日终焉"
    assert signals[0].genre == "悬疑脑洞"
    assert signals[0].tags == ["悬疑脑洞", "都市脑洞"]
    assert "普通密室逃脱" in signals[0].summary
    assert signals[1].genre == "都市高武"


def test_collect_fanqie_rank_decodes_known_font_obfuscation():
    html = """
    <div class="rank-book-item">
      <div class="title"><a href="/page/7231424472606051384" class="font-DNMrHsV173Pd4pgy">惹枝</a></div>
      <div class="desc abstract font-DNMrHsV173Pd4pgy">(影视版权售，签约版)</div>
    </div>
    <div class="rank-book-item">
      <div class="title"><a href="/page/7352423170789366799" class="font-DNMrHsV173Pd4pgy">指挥掌谋妻</a></div>
      <div class="desc abstract font-DNMrHsV173Pd4pgy">穿越警撞锦衣卫指挥。</div>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="fanqie_rank",
        name="番茄-小说榜",
        url="https://fanqienovel.com/rank",
        category="novel",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "惹金枝"
    assert "已售出" in signals[0].summary
    assert signals[1].title == "指挥使的掌心谋妻"
    assert "特警女主" in signals[1].summary


def test_collect_fanqie_rank_does_not_use_author_as_genre_when_tags_missing():
    html = """
    <div class="rank-book-item">
      <div class="title"><a href="/page/123">惹金枝</a></div>
      <div class="author"><a href="/author-page/1">空留</a></div>
      <div class="desc abstract">(影视版权已售出，已签约出版)</div>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="fanqie_rank",
        name="番茄-小说榜",
        url="https://fanqienovel.com/rank",
        category="novel",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=1,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "惹金枝"
    assert signals[0].genre == ""
    assert signals[0].tags == []


def test_collect_tencent_comic_rank_extracts_rank_metadata():
    html = """
    <div class="ran-rank-month-tit clearfix">
      <a href="/Rank/comicRank/type/mt"><h3 class="ran-rank-title ui-left">月票榜</h3></a>
    </div>
    <ol class="mod-rank-list mod-rank-month-list">
      <li>
        <sub class="mod-rank-keep ui-left">1</sub>
        <a class="mod-rank-name text-overflow ui-left" title="我是大神仙" href="/Comic/ComicInfo/id/621058">我是大神仙</a>
        <span class="mod-rank-num ui-right">6015 张</span>
      </li>
      <li>
        <sub class="mod-rank-keep ui-left">2</sub>
        <a class="mod-rank-name text-overflow ui-left" title="敖敖待捕" href="/Comic/ComicInfo/id/637865">敖敖待捕</a>
        <span class="mod-rank-num ui-right">4578 张</span>
      </li>
    </ol>
    """
    source = TopicMarketSignalSourceDTO(
        key="tencent_comic_rank",
        name="腾讯动漫-漫画榜",
        url="https://ac.qq.com/Rank/comicRank/type/pgv",
        category="comic",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "我是大神仙"
    assert signals[0].genre == "漫画"
    assert signals[0].tags == ["漫画", "月票榜"]
    assert "月票榜第1名" in signals[0].summary
    assert "6015 张" in signals[0].summary
    assert signals[1].title == "敖敖待捕"


def test_collect_kuaikan_comic_rank_extracts_rank_metadata():
    html = """
    <div class="rankList fl">
      <h3 class="title">人气榜<a href="/ranking/9" class="more fr">更多</a></h3>
      <div data-index="0" class="listItem">
        <div class="normal">
          <span class="top no_1">1</span>
          <span class="title">错撩</span>
          <span class="author fr">翘摇（原著）+绿绿绿酱</span>
        </div>
        <div class="hover cls">
          <div class="imgBox fl"><a href="/web/topic/21881"></a></div>
          <div class="info fr">
            <div class="title"><span>错撩</span></div>
            <p class="author">翘摇（原著）+绿绿绿酱</p>
            <div class="detailBox">
              <p class="description">财经美女记者郑书意遭遇渣男劈腿，转身开启泡总裁计划。</p>
              <a href="/web/comic/839431" class="update">更新至：周日更新</a>
            </div>
          </div>
        </div>
      </div>
      <div data-index="1" class="listItem">
        <div class="normal">
          <span class="top no_2">2</span>
          <span class="title">风之誓，恋之咒</span>
          <span class="author fr">有点笔格工作室</span>
        </div>
      </div>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="kuaikan_comic",
        name="快看漫画-漫画",
        url="https://www.kuaikanmanhua.com/ranking/",
        category="comic",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "错撩"
    assert signals[0].genre == "漫画"
    assert signals[0].tags == ["漫画", "人气榜"]
    assert "人气榜第1名" in signals[0].summary
    assert "绿绿绿酱" in signals[0].summary
    assert "泡总裁计划" in signals[0].summary
    assert "周日更新" in signals[0].summary
    assert signals[1].title == "风之誓，恋之咒"


def test_collect_kuaikan_single_rank_page_extracts_item_titles():
    html = """
    <title>人气榜_漫画排行榜_快看漫画</title>
    <div class="RankingNav"><a title="人气榜" class="active">人气榜</a></div>
    <div class="IdItems fl">
      <a href="/web/topic/27584" class="itemLink cls">
        <div class="details fl">
          <div class="title cls">
            <span class="text"><div class="RankIcon icons"><span class="iconText bg_4">4</span></div><span>飘飘</span></span>
          </div>
          <div class="author">红鲤</div>
          <div class="desc">都市恋爱与职场成长。</div>
        </div>
      </a>
    </div>
    <div class="IdItems fl">
      <a href="/web/topic/15710" class="itemLink cls">
        <div class="details fl">
          <div class="title cls"><span class="text"><span>偏偏宠爱</span></span></div>
          <div class="author">藤萝为枝</div>
        </div>
      </a>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="kuaikan_comic",
        name="快看漫画-漫画",
        url="https://www.kuaikanmanhua.com/ranking/9",
        category="comic",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert [item.title for item in signals] == ["飘飘", "偏偏宠爱"]
    assert signals[0].tags == ["漫画", "人气榜"]
    assert "都市恋爱与职场成长" in signals[0].summary


def test_collect_jjwxc_rank_extracts_book_links_and_rank_name():
    html = """
    <div class="b module">
      <h2 class="big o">
        <span class="half"><a class="channellink" href="/rank/naturalmore/5">新文排行榜&gt;&gt;</a></span>
        <span class="half"><a class="channellink" href="/rank/naturalmore/6">霸王票排行榜&gt;&gt;</a></span>
      </h2>
      <table class="double_column">
        <tr>
          <td>
            <ul>
              <li><a href="/book2/10274506">春夜困渡</a></li>
              <li><a href="/book2/10282981">她比星光更难追</a><span style="color:#009900">*</span></li>
            </ul>
          </td>
        </tr>
      </table>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="jjwxc_rank",
        name="晋江-小说榜",
        url="https://m.jjwxc.net/rank",
        category="novel",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "春夜困渡"
    assert signals[0].genre == "新文排行榜"
    assert signals[0].tags == ["晋江", "新文排行榜"]
    assert "新文排行榜第1名" in signals[0].summary
    assert signals[1].title == "她比星光更难追"


def test_collect_qimao_rank_extracts_book_metadata():
    html = """
    <div class="rank-list-wrap">
      <div class="header"><span class="header-txt">大热榜</span></div>
      <ul class="rank-list">
        <li class="rank-list-item">
          <span class="rank-number first">1</span>
          <a href="https://www.qimao.com/shuku/195958/" class="s-book-title">盖世神医</a>
          <span class="s-book-info clearfix">
            <a href="/zuozhe/1/">狐颜乱语</a>
            <a href="/shuku/a-203-a-a-a-a-a-click-1/">都市</a>
            <a href="/shuku/a-203-219-a-a-a-a-click-1/">都市高武</a>
            <em>连载中</em><em>850.34万字</em>
          </span>
          <span class="s-book-intro">任你权势滔天，任你富可敌国，在我面前不要嚣张。</span>
          <span class="rank-change-num"><em class="rank-num">160.0</em><em class="rank-unit">万</em><em>热度</em></span>
        </li>
        <li class="rank-list-item">
          <span class="rank-number second">2</span>
          <a href="https://www.qimao.com/shuku/1834789/" class="s-book-title">警报！真龙出狱！</a>
          <span class="s-book-info clearfix">
            <a href="/zuozhe/2/">红透半边天</a>
            <a href="/shuku/a-203-a-a-a-a-a-click-1/">都市</a>
            <a href="/shuku/a-203-220-a-a-a-a-click-1/">都市高手</a>
            <em>连载中</em><em>298.85万字</em>
          </span>
          <span class="s-book-intro">叶楚替兄长顶罪入狱，三年后王者归来。</span>
          <span class="rank-change-num"><em class="rank-num">122.8</em><em class="rank-unit">万</em><em>热度</em></span>
        </li>
      </ul>
    </div>
    """
    source = TopicMarketSignalSourceDTO(
        key="qimao_rank",
        name="七猫-小说榜",
        url="https://www.qimao.com/paihang",
        category="novel",
        source_type="public_page",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: html,
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals[0].title == "盖世神医"
    assert signals[0].genre == "都市"
    assert signals[0].tags == ["都市", "都市高武", "大热榜"]
    assert "大热榜第1名" in signals[0].summary
    assert "160.0万热度" in signals[0].summary
    assert "权势滔天" in signals[0].summary
    assert signals[1].title == "警报！真龙出狱！"


def test_build_market_signal_collectors_includes_future_source_types():
    collectors = build_market_signal_collectors()

    assert "public_page" in collectors
    assert "api" in collectors
    assert "authenticated_source" in collectors


def test_collect_market_signals_from_unsupported_source_type_returns_empty():
    source = TopicMarketSignalSourceDTO(
        key="future_api",
        name="未来 API 源",
        url="https://example.com/api",
        category="novel",
        source_type="api",
        requires_auth=False,
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: "",
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals == []


def test_collect_market_signals_from_requires_auth_source_returns_empty():
    source = TopicMarketSignalSourceDTO(
        key="future_auth",
        name="未来登录态源",
        url="https://example.com/auth",
        category="novel",
        source_type="authenticated_source",
        requires_auth=True,
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: "",
        limit=2,
        collectors=build_market_signal_collectors(),
    )

    assert signals == []


def test_collect_market_signals_passes_credentials_to_authenticated_collector():
    class CredentialAwareCollector:
        source_type = "authenticated_source"

        def __init__(self):
            self.credentials = None

        def collect(self, source, fetch_text, limit, credentials=None):
            self.credentials = credentials
            return [
                TopicMarketSignalDTO(
                    id="signal-auth",
                    source=source.name,
                    title="登录态榜单",
                )
            ]

    collector = CredentialAwareCollector()
    source = TopicMarketSignalSourceDTO(
        key="future_auth",
        name="未来登录态源",
        url="https://example.com/auth",
        category="novel",
        source_type="authenticated_source",
        requires_auth=True,
    )
    credentials = TopicMarketSignalSourceCredentialDTO(
        source_key="future_auth",
        cookie="session=abc",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=lambda _url: "",
        limit=2,
        collectors={"authenticated_source": collector},
        credentials=credentials,
    )

    assert signals[0].title == "登录态榜单"
    assert collector.credentials == credentials


def test_public_page_collector_uses_credentials_as_request_headers():
    captured = {}

    def fetch_text(_url, headers):
        captured.update(headers)
        return "<html><h2>债务修仙</h2></html>"

    source = TopicMarketSignalSourceDTO(
        key="qidian_rank",
        name="起点-小说榜",
        url="https://www.qidian.com/rank/",
        category="novel",
        source_type="public_page",
        requires_auth=False,
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=fetch_text,
        limit=1,
        collectors=build_market_signal_collectors(),
        credentials=TopicMarketSignalSourceCredentialDTO(
            source_key="qidian_rank",
            api_key="key-123",
            cookie="session=abc",
            headers={"X-Platform": "qidian"},
        ),
    )

    assert signals[0].title == "债务修仙"
    assert captured["Authorization"] == "Bearer key-123"
    assert captured["Cookie"] == "session=abc"
    assert captured["X-Platform"] == "qidian"


def test_api_collector_extracts_market_signals_from_json_payload():
    captured = {}

    def fetch_text(_url, headers):
        captured.update(headers)
        return """
        {
          "data": {
            "rankName": "热读榜",
            "books": [
              {
                "bookName": "债务修仙",
                "category": "玄幻",
                "tags": ["负债", "升级"],
                "intro": "主角背债入仙门，用债务规则推动升级。",
                "heat": "160万热度"
              },
              {
                "bookName": "契约少女",
                "category": "恋爱",
                "tags": "契约,错撩",
                "description": "契约关系推动连续误会。",
                "rank": 2
              }
            ]
          }
        }
        """

    source = TopicMarketSignalSourceDTO(
        key="future_api",
        name="未来 API 源",
        url="https://example.com/api/rank",
        category="novel",
        source_type="api",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=fetch_text,
        limit=2,
        collectors=build_market_signal_collectors(),
        credentials=TopicMarketSignalSourceCredentialDTO(
            source_key="future_api",
            api_key="key-123",
            cookie="session=abc",
        ),
    )

    assert [item.title for item in signals] == ["债务修仙", "契约少女"]
    assert signals[0].genre == "玄幻"
    assert signals[0].tags == ["负债", "升级", "热读榜"]
    assert "热读榜第1名" in signals[0].summary
    assert "160万热度" in signals[0].summary
    assert "债务规则推动升级" in signals[0].summary
    assert signals[1].tags == ["契约", "错撩", "热读榜"]
    assert captured["Authorization"] == "Bearer key-123"
    assert captured["Cookie"] == "session=abc"


def test_api_collector_extracts_category_list_metadata_from_json_payload():
    def fetch_text(_url, _headers):
        return """
        {
          "data": {
            "column": {
              "books": [
                {
                  "title": "苟在武道世界成圣",
                  "category": "3",
                  "categories": [
                    {"name": "小说"},
                    {"name": "玄幻"},
                    {"name": "东方玄幻"}
                  ],
                  "intro": "命格在手，苟道求生。"
                }
              ]
            }
          }
        }
        """

    source = TopicMarketSignalSourceDTO(
        key="qq_read",
        name="腾讯-QQ阅读",
        url="https://ubook.reader.qq.com/api/book/rank?columnId=535193&pageIndex=1&pageSize=20",
        category="novel",
        source_type="api",
    )

    signals = collect_market_signals_from_source(
        source=source,
        fetch_text=fetch_text,
        limit=1,
        collectors=build_market_signal_collectors(),
        credentials=TopicMarketSignalSourceCredentialDTO(source_key="qq_read", cookie="session=abc"),
    )

    assert signals[0].title == "苟在武道世界成圣"
    assert signals[0].genre == "玄幻"
    assert signals[0].tags == ["玄幻", "东方玄幻"]
    assert "苟道求生" in signals[0].summary
