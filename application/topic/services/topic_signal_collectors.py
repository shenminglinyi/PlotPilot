"""市场信号采集器抽象。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from html import unescape
import inspect
from typing import Callable
from uuid import uuid4

from application.topic.dtos import (
    TopicMarketSignalDTO,
    TopicMarketSignalSourceCredentialDTO,
    TopicMarketSignalSourceDTO,
)

logger = logging.getLogger(__name__)

_FANQIE_TEXT_FONT_MAP = {
    "58670": "0", "58413": "1", "58678": "2", "58371": "3", "58353": "4", "58480": "5",
    "58359": "6", "58449": "7", "58540": "8", "58692": "9", "58712": "a", "58542": "b",
    "58575": "c", "58626": "d", "58691": "e", "58561": "f", "58362": "g", "58619": "h",
    "58430": "i", "58531": "j", "58588": "k", "58440": "l", "58681": "m", "58631": "n",
    "58376": "o", "58429": "p", "58555": "q", "58498": "r", "58518": "s", "58453": "t",
    "58397": "u", "58356": "v", "58435": "w", "58514": "x", "58482": "y", "58529": "z",
    "58515": "A", "58688": "B", "58709": "C", "58344": "D", "58656": "E", "58381": "F",
    "58576": "G", "58516": "H", "58463": "I", "58649": "J", "58571": "K", "58558": "L",
    "58433": "M", "58517": "N", "58387": "O", "58687": "P", "58537": "Q", "58541": "R",
    "58458": "S", "58390": "T", "58466": "U", "58386": "V", "58697": "W", "58519": "X",
    "58511": "Y", "58634": "Z", "58611": "的", "58590": "一", "58398": "是", "58422": "了",
    "58657": "我", "58666": "不", "58562": "人", "58345": "在", "58510": "他", "58496": "有",
    "58654": "这", "58441": "个", "58493": "上", "58714": "们", "58618": "来", "58528": "到",
    "58620": "时", "58403": "大", "58461": "地", "58481": "为", "58700": "子", "58708": "中",
    "58503": "你", "58442": "说", "58639": "生", "58506": "国", "58663": "年", "58436": "着",
    "58563": "就", "58391": "那", "58357": "和", "58354": "要", "58695": "她", "58372": "出",
    "58696": "也", "58551": "得", "58445": "里", "58408": "后", "58599": "自", "58424": "以",
    "58394": "会", "58348": "家", "58426": "可", "58673": "下", "58417": "而", "58556": "过",
    "58603": "天", "58565": "去", "58604": "能", "58522": "对", "58632": "小", "58622": "多",
    "58350": "然", "58605": "于", "58617": "心", "58401": "学", "58637": "么", "58684": "之",
    "58382": "都", "58464": "好", "58487": "看", "58693": "起", "58608": "发", "58392": "当",
    "58474": "没", "58601": "成", "58355": "只", "58573": "如", "58499": "事", "58469": "把",
    "58361": "还", "58698": "用", "58489": "第", "58711": "样", "58457": "道", "58635": "想",
    "58492": "作", "58647": "种", "58623": "开", "58521": "美", "58609": "总", "58530": "从",
    "58665": "无", "58652": "情", "58676": "已", "58456": "面", "58581": "最", "58509": "女",
    "58488": "但", "58363": "现", "58685": "前", "58396": "些", "58523": "所", "58471": "同",
    "58485": "日", "58613": "手", "58533": "又", "58589": "行", "58527": "意", "58593": "动",
    "58699": "方", "58707": "期", "58414": "它", "58596": "头", "58570": "经", "58660": "长",
    "58364": "儿", "58526": "回", "58501": "位", "58638": "分", "58404": "爱", "58677": "老",
    "58535": "因", "58629": "很", "58577": "给", "58606": "名", "58497": "法", "58662": "间",
    "58479": "斯", "58532": "知", "58380": "世", "58385": "什", "58405": "两", "58644": "次",
    "58578": "使", "58505": "身", "58564": "者", "58412": "被", "58686": "高", "58624": "已",
    "58667": "亲", "58607": "其", "58616": "进", "58368": "此", "58427": "话", "58423": "常",
    "58633": "与", "58525": "活", "58543": "正", "58418": "感", "58597": "见", "58683": "明",
    "58507": "问", "58621": "力", "58703": "理", "58438": "尔", "58536": "点", "58384": "文",
    "58484": "几", "58539": "定", "58554": "本", "58421": "公", "58347": "特", "58569": "做",
    "58710": "外", "58574": "孩", "58375": "相", "58645": "西", "58592": "果", "58572": "走",
    "58388": "将", "58370": "月", "58399": "十", "58651": "实", "58546": "向", "58504": "声",
    "58419": "车", "58407": "全", "58672": "信", "58675": "重", "58538": "三", "58465": "机",
    "58374": "工", "58579": "物", "58402": "气", "58702": "每", "58553": "并", "58360": "别",
    "58389": "真", "58560": "打", "58690": "太", "58473": "新", "58512": "比", "58653": "才",
    "58704": "便", "58545": "夫", "58641": "再", "58475": "书", "58583": "部", "58472": "水",
    "58478": "像", "58664": "眼", "58586": "等", "58568": "体", "58674": "却", "58490": "加",
    "58476": "电", "58346": "主", "58630": "界", "58595": "门", "58502": "利", "58713": "海",
    "58587": "受", "58548": "听", "58351": "表", "58547": "徳", "58443": "少", "58460": "克",
    "58636": "代", "58585": "员", "58625": "许", "58694": "稜", "58428": "先", "58640": "口",
    "58628": "由", "58612": "死", "58446": "安", "58468": "写", "58410": "性", "58508": "马",
    "58594": "光", "58483": "白", "58544": "或", "58495": "住", "58450": "难", "58643": "望",
    "58486": "教", "58406": "命", "58447": "花", "58669": "结", "58415": "乐", "58444": "色",
    "58549": "更", "58494": "拉", "58409": "东", "58658": "神", "58557": "记", "58602": "处",
    "58559": "让", "58610": "母", "58513": "父", "58500": "应", "58378": "直", "58680": "字",
    "58352": "场", "58383": "平", "58454": "报", "58671": "友", "58668": "关", "58452": "放",
    "58627": "至", "58400": "张", "58455": "认", "58416": "接", "58552": "告", "58614": "入",
    "58582": "笑", "58534": "内", "58701": "英", "58349": "军", "58491": "侯", "58467": "民",
    "58365": "岁", "58598": "往", "58425": "何", "58462": "度", "58420": "山", "58661": "觉",
    "58615": "路", "58648": "带", "58470": "万", "58377": "男", "58520": "边", "58646": "风",
    "58600": "解", "58431": "叫", "58715": "任", "58524": "金", "58439": "快", "58566": "原",
    "58477": "吃", "58642": "妈", "58437": "变", "58411": "通", "58451": "师", "58395": "立",
    "58369": "象", "58706": "数", "58705": "四", "58379": "失", "58567": "满", "58373": "战",
    "58448": "远", "58659": "格", "58434": "士", "58679": "音", "58432": "轻", "58689": "目",
    "58591": "条", "58682": "呢",
}


class MarketSignalCollector:
    """统一采集器接口。"""

    source_type = ""

    def collect(
        self,
        source: TopicMarketSignalSourceDTO,
        fetch_text: Callable[[str], str],
        limit: int,
        credentials: TopicMarketSignalSourceCredentialDTO | None = None,
    ) -> list[TopicMarketSignalDTO]:
        raise NotImplementedError


class PublicPageMarketSignalCollector(MarketSignalCollector):
    """公开页面抓取采集器。"""

    source_type = "public_page"

    def collect(
        self,
        source: TopicMarketSignalSourceDTO,
        fetch_text: Callable[[str], str],
        limit: int,
        credentials: TopicMarketSignalSourceCredentialDTO | None = None,
    ) -> list[TopicMarketSignalDTO]:
        try:
            html = _fetch_with_optional_headers(
                fetch_text,
                source.url,
                _headers_from_credentials(credentials),
            )
        except Exception as exc:
            logger.warning("market signal collection failed for %s: %s", source.key, exc)
            return []
        if source.key == "qidian_rank":
            signals = _signals_from_qidian_rank_html(source, html, limit)
            if signals:
                return signals
        if source.key == "jjwxc_rank":
            signals = _signals_from_jjwxc_rank_html(source, html, limit)
            if signals:
                return signals
        if source.key == "qimao_rank":
            signals = _signals_from_qimao_rank_html(source, html, limit)
            if signals:
                return signals
        if source.key == "fanqie_rank":
            signals = _signals_from_fanqie_rank_html(source, html, limit)
            if signals:
                return signals
        if source.key == "tencent_comic_rank":
            signals = _signals_from_tencent_comic_rank_html(source, html, limit)
            if signals:
                return signals
        if source.key == "kuaikan_comic":
            signals = _signals_from_kuaikan_comic_rank_html(source, html, limit)
            if signals:
                return signals
        return _signals_from_html(source, html, limit)


class ApiMarketSignalCollector(MarketSignalCollector):
    """未来 API 采集器占位。"""

    source_type = "api"

    def collect(
        self,
        source: TopicMarketSignalSourceDTO,
        fetch_text: Callable[[str], str],
        limit: int,
        credentials: TopicMarketSignalSourceCredentialDTO | None = None,
    ) -> list[TopicMarketSignalDTO]:
        if not _has_credentials(credentials):
            logger.info("market signal api source %s is not configured yet", source.key)
            return []
        try:
            text = _fetch_with_optional_headers(
                fetch_text,
                source.url,
                _headers_from_credentials(credentials),
            )
        except Exception as exc:
            logger.warning("market signal api collection failed for %s: %s", source.key, exc)
            return []
        signals = _signals_from_api_json(source, text, limit)
        if signals:
            return signals
        return _signals_from_html(source, text, limit)


class AuthenticatedSourceMarketSignalCollector(MarketSignalCollector):
    """未来登录态采集器占位。"""

    source_type = "authenticated_source"

    def collect(
        self,
        source: TopicMarketSignalSourceDTO,
        fetch_text: Callable[[str], str],
        limit: int,
        credentials: TopicMarketSignalSourceCredentialDTO | None = None,
    ) -> list[TopicMarketSignalDTO]:
        if not _has_credentials(credentials):
            logger.info("market signal authenticated source %s is not configured yet", source.key)
            return []
        try:
            text = _fetch_with_optional_headers(
                fetch_text,
                source.url,
                _headers_from_credentials(credentials),
            )
        except Exception as exc:
            logger.warning("market signal authenticated collection failed for %s: %s", source.key, exc)
            return []
        return _signals_from_html(source, text, limit)


def build_market_signal_collectors() -> dict[str, MarketSignalCollector]:
    return {
        PublicPageMarketSignalCollector.source_type: PublicPageMarketSignalCollector(),
        ApiMarketSignalCollector.source_type: ApiMarketSignalCollector(),
        AuthenticatedSourceMarketSignalCollector.source_type: AuthenticatedSourceMarketSignalCollector(),
    }


def collect_market_signals_from_source(
    source: TopicMarketSignalSourceDTO,
    fetch_text: Callable[[str], str],
    limit: int,
    collectors: dict[str, MarketSignalCollector],
    credentials: TopicMarketSignalSourceCredentialDTO | None = None,
) -> list[TopicMarketSignalDTO]:
    collector = collectors.get(str(source.source_type or "").strip())
    if collector is None:
        logger.info(
            "market signal source %s skipped: unsupported source_type=%s",
            source.key,
            source.source_type,
        )
        return []
    if source.requires_auth and not _has_credentials(credentials):
        logger.info("market signal source %s skipped: requires auth", source.key)
        return []
    return collector.collect(
        source=source,
        fetch_text=fetch_text,
        limit=limit,
        credentials=credentials,
    )


def _has_credentials(credentials: TopicMarketSignalSourceCredentialDTO | None) -> bool:
    return bool(
        credentials
        and (
            str(credentials.api_key or "").strip()
            or str(credentials.cookie or "").strip()
            or str(credentials.endpoint_url or "").strip()
            or credentials.headers
        )
    )


def _headers_from_credentials(
    credentials: TopicMarketSignalSourceCredentialDTO | None,
) -> dict[str, str]:
    headers = {
        str(key).strip(): str(value).strip()
        for key, value in ((credentials.headers if credentials else {}) or {}).items()
        if str(key).strip() and str(value).strip()
    }
    if credentials and credentials.api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {credentials.api_key}"
    if credentials and credentials.cookie and "Cookie" not in headers:
        headers["Cookie"] = credentials.cookie
    return headers


def _fetch_with_optional_headers(
    fetch_text: Callable[[str], str],
    url: str,
    headers: dict[str, str],
) -> str:
    try:
        parameters = inspect.signature(fetch_text).parameters
        accepts_headers = any(
            parameter.kind == inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters.values()
        ) or len(parameters) >= 2
    except (TypeError, ValueError):
        accepts_headers = False
    if accepts_headers:
        return fetch_text(url, headers)
    return fetch_text(url)


def _signals_from_api_json(
    source: TopicMarketSignalSourceDTO,
    payload: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    try:
        data = json.loads(payload or "")
    except (TypeError, json.JSONDecodeError):
        return []
    rank_name = _json_first_text_recursive(data, ("rankName", "rank_name", "榜单", "榜名"))
    candidates = _json_candidate_items(data)
    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = _json_first_text(
            item,
            ("title", "bookName", "book_name", "name", "comicName", "comic_name"),
        )
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        genre = _json_genre(item)
        tags = _json_tags(item, rank_name)
        summary = _json_summary(source, title, item, rank_name, len(signals) + 1)
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre=genre or ("漫画" if source.category == "comic" else ""),
                tags=tags,
                summary=summary,
                raw_text=json.dumps(item, ensure_ascii=False),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _json_candidate_items(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("books", "items", "list", "records", "data", "result", "rankList"):
        nested = value.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            items = _json_candidate_items(nested)
            if items:
                return items
    for nested in value.values():
        items = _json_candidate_items(nested)
        if items:
            return items
    return []


def _json_first_text(value: object, keys: tuple[str, ...]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        text = str(value.get(key) or "").strip()
        if text:
            return re.sub(r"\s+", " ", text)
    return ""


def _json_first_text_recursive(value: object, keys: tuple[str, ...]) -> str:
    text = _json_first_text(value, keys)
    if text:
        return text
    if isinstance(value, dict):
        for nested in value.values():
            text = _json_first_text_recursive(nested, keys)
            if text:
                return text
    if isinstance(value, list):
        for nested in value:
            text = _json_first_text_recursive(nested, keys)
            if text:
                return text
    return ""


def _json_tags(item: dict[str, object], rank_name: str) -> list[str]:
    tags: list[str] = []
    for key in ("tags", "tag", "keywords", "labels", "categories"):
        value = item.get(key)
        if isinstance(value, list):
            candidates = value
        else:
            candidates = re.split(r"[,，/、\s]+", str(value or ""))
        for candidate in candidates:
            text = _json_tag_text(candidate)
            if text and text not in {"小说", "漫画"} and text not in tags:
                tags.append(text)
    if rank_name and rank_name not in tags:
        tags.append(rank_name)
    return tags[:5]


def _json_genre(item: dict[str, object]) -> str:
    genre = _json_first_text(item, ("category", "genre", "type", "className", "class_name"))
    if genre and not genre.isdigit():
        return genre
    categories = item.get("categories")
    if isinstance(categories, list):
        names = [
            _json_tag_text(category)
            for category in categories
            if isinstance(category, dict)
        ]
        names = [name for name in names if name and name not in {"小说", "漫画"}]
        return names[0] if names else ""
    return ""


def _json_tag_text(value: object) -> str:
    if isinstance(value, dict):
        return _json_first_text(value, ("name", "shortName", "short_name", "title", "label"))
    return str(value or "").strip()


def _json_summary(
    source: TopicMarketSignalSourceDTO,
    title: str,
    item: dict[str, object],
    rank_name: str,
    fallback_rank: int,
) -> str:
    rank = _json_first_text(item, ("rank", "ranking", "rankNo", "rank_no")) or str(fallback_rank)
    intro = _json_first_text(item, ("intro", "description", "summary", "desc"))
    heat = _json_first_text(item, ("heat", "hot", "popularity", "score", "metric"))
    prefix = f"{source.name} {rank_name}第{rank}名：{title}" if rank_name else f"{source.name} API 信号：{title}"
    parts = [prefix]
    if heat:
        parts.append(heat)
    if intro:
        parts.append(intro)
    return "；".join(parts)[:240]


def _signals_from_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    text = re.sub(r"<(script|style).*?</\1>", " ", html or "", flags=re.I | re.S)
    candidates = re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", text, flags=re.I | re.S)
    if not candidates:
        candidates = re.findall(r'title=["\']([^"\']{2,60})["\']', text, flags=re.I)
    plain = unescape(re.sub(r"<[^>]+>", "\n", text))
    lines = [line.strip() for line in plain.splitlines() if line.strip()]
    if not candidates:
        candidates = lines

    seen = set()
    signals: list[TopicMarketSignalDTO] = []
    for candidate in candidates:
        title = unescape(re.sub(r"<[^>]+>", "", candidate)).strip()
        title = re.sub(r"\s+", " ", title)
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        summary = _summary_for_collected_title(title, lines)
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre="漫画" if source.category == "comic" else "",
                tags=["漫画"] if source.category == "comic" else [],
                summary=summary or f"{source.name} 公开页面出现：{title}",
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _signals_from_qidian_rank_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    blocks = re.findall(
        r'<div[^>]+class=["\'][^"\']*book-mid-info[^"\']*["\'][^>]*>(.*?)</div>',
        html or "",
        flags=re.I | re.S,
    )
    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for block in blocks:
        title = _first_link_text(block, r"<h2[^>]*>(.*?)</h2>")
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        metadata = _qidian_metadata(block)
        summary = _qidian_intro(block) or f"{source.name} 公开页面出现：{title}"
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre=metadata[0] if metadata else "",
                tags=metadata[:2],
                summary=summary,
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    if signals:
        return signals
    return _signals_from_qidian_mobile_rank_html(source, html, limit)


def _signals_from_qidian_mobile_rank_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    item_matches = list(
        re.finditer(
            r'<a[^>]+href=["\'][^"\']*m\.qidian\.com/book/\d+/?[^"\']*["\'][^>]*>.*?</a>',
            html or "",
            flags=re.I | re.S,
        )
    )
    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for item_match in item_matches:
        block = item_match.group(0)
        title_match = re.search(r"<h2[^>]*>(.*?)</h2>", block, flags=re.I | re.S)
        title = _clean_html_text(title_match.group(1)) if title_match else ""
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        rank_name = _nearest_qidian_mobile_rank_title(html or "", item_match.start()) or "起点榜单"
        rank = _qidian_mobile_rank_text(block) or str(len(signals) + 1)
        metadata = _qidian_mobile_metadata(block)
        tags = ([metadata[0]] if metadata else []) + [rank_name]
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre=metadata[0] if metadata else rank_name,
                tags=tags[:3],
                summary=f"{source.name} {rank_name}第{rank}名：{title}",
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _signals_from_jjwxc_rank_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    rank_name = _jjwxc_rank_name(html) or "晋江榜单"
    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for link_match in re.finditer(
        r'<a[^>]+href=["\'][^"\']*/book2/\d+[^"\']*["\'][^>]*>(.*?)</a>',
        html or "",
        flags=re.I | re.S,
    ):
        title = _clean_html_text(link_match.group(1))
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        rank = len(signals) + 1
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre=rank_name,
                tags=["晋江", rank_name],
                summary=f"{source.name} {rank_name}第{rank}名：{title}",
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _signals_from_qimao_rank_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    rank_name = _qimao_rank_name(html) or "七猫榜单"
    item_matches = re.finditer(
        r'<li[^>]+class=["\'][^"\']*rank-list-item[^"\']*["\'][^>]*>.*?</li>',
        html or "",
        flags=re.I | re.S,
    )
    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for item_match in item_matches:
        block = item_match.group(0)
        title = _qimao_title(block)
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        tags = _qimao_tags(block)
        rank = _qimao_rank_text(block) or str(len(signals) + 1)
        metric = _qimao_metric(block)
        intro = _qimao_intro(block)
        summary_parts = [f"{source.name} {rank_name}第{rank}名：{title}"]
        if metric:
            summary_parts.append(metric)
        if intro:
            summary_parts.append(intro)
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre=tags[0] if tags else rank_name,
                tags=(tags + [rank_name])[:3],
                summary="；".join(summary_parts),
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _signals_from_fanqie_rank_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    card_starts = list(
        re.finditer(
            r'<(?:div|li|article)[^>]+class=["\'][^"\']*(?:muye-rank-book-item|rank-book-item|book-card|book-item)[^"\']*["\'][^>]*>',
            html or "",
            flags=re.I | re.S,
        )
    )
    blocks = [
        (html or "")[
            match.start():card_starts[index + 1].start()
            if index + 1 < len(card_starts)
            else min(len(html or ""), match.start() + 2500)
        ]
        for index, match in enumerate(card_starts)
    ]
    if not blocks:
        blocks = [
            (html or "")[max(0, match.start() - 500):min(len(html or ""), match.end() + 1200)]
            for match in re.finditer(
                r'<a[^>]+href=["\'][^"\']*/page/\d+[^"\']*["\'][^>]*>.*?</a>',
                html or "",
                flags=re.I | re.S,
            )
        ]

    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for block in blocks:
        title = _fanqie_title(block)
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        tags = _fanqie_tags(block, title)
        summary = _fanqie_summary(block) or f"{source.name} 公开页面出现：{title}"
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre=tags[0] if tags else "",
                tags=tags[:3],
                summary=summary,
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _signals_from_tencent_comic_rank_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    item_matches = re.finditer(r"<li[^>]*>.*?</li>", html or "", flags=re.I | re.S)
    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for item_match in item_matches:
        block = item_match.group(0)
        if "mod-rank-name" not in block:
            continue
        link_match = re.search(
            r'(<a[^>]+class=["\'][^"\']*mod-rank-name[^"\']*["\'][^>]*>)(.*?)</a>',
            block,
            flags=re.I | re.S,
        )
        if not link_match:
            continue
        title_attr = re.search(r'title=["\']([^"\']+)["\']', link_match.group(1), flags=re.I)
        title = _clean_html_text(title_attr.group(1) if title_attr else link_match.group(2))
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        rank = _tencent_rank_text(block)
        rank_name = _nearest_tencent_rank_title(html or "", item_match.start()) or "漫画榜"
        metric = _tencent_rank_metric(block)
        summary = f"{source.name} {rank_name}第{rank}名：{title}"
        if metric:
            summary = f"{summary}，{metric}"
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre="漫画",
                tags=["漫画", rank_name],
                summary=summary,
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _signals_from_kuaikan_comic_rank_html(
    source: TopicMarketSignalSourceDTO,
    html: str,
    limit: int,
) -> list[TopicMarketSignalDTO]:
    item_starts = list(
        re.finditer(
            r'<div[^>]+class=["\'][^"\']*listItem[^"\']*["\'][^>]*>',
            html or "",
            flags=re.I | re.S,
        )
    )
    blocks = [
        (html or "")[
            match.start():item_starts[index + 1].start()
            if index + 1 < len(item_starts)
            else min(len(html or ""), match.start() + 3500)
        ]
        for index, match in enumerate(item_starts)
    ]

    signals: list[TopicMarketSignalDTO] = []
    seen: set[str] = set()
    for index, block in enumerate(blocks):
        title = _kuaikan_title(block)
        if not _is_signal_title(title) or title in seen:
            continue
        seen.add(title)
        rank_name = _nearest_kuaikan_rank_title(html or "", item_starts[index].start()) or "快看榜单"
        rank = _kuaikan_rank_text(block) or str(index + 1)
        author = _kuaikan_author(block)
        description = _kuaikan_description(block)
        update = _kuaikan_update(block)
        summary_parts = [f"{source.name} {rank_name}第{rank}名：{title}"]
        if author:
            summary_parts.append(author)
        if description:
            summary_parts.append(description)
        if update:
            summary_parts.append(update)
        signals.append(
            TopicMarketSignalDTO(
                id=f"signal-{uuid4().hex}",
                source=source.name,
                title=title,
                genre="漫画",
                tags=["漫画", rank_name],
                summary="；".join(summary_parts),
                raw_text=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(signals) >= limit:
            break
    return signals


def _first_link_text(block: str, container_pattern: str) -> str:
    container_match = re.search(container_pattern, block or "", flags=re.I | re.S)
    text = container_match.group(1) if container_match else block
    link_match = re.search(r"<a[^>]*>(.*?)</a>", text, flags=re.I | re.S)
    if link_match:
        text = link_match.group(1)
    return _clean_html_text(text)


def _jjwxc_rank_name(html: str) -> str:
    channel_match = re.search(
        r'<a[^>]+class=["\'][^"\']*channellink[^"\']*["\'][^>]*>(.*?)</a>',
        html or "",
        flags=re.I | re.S,
    )
    if channel_match:
        return _normalize_rank_name(channel_match.group(1))
    heading_match = re.search(r"<h2[^>]*>(.*?)</h2>", html or "", flags=re.I | re.S)
    return _normalize_rank_name(heading_match.group(1)) if heading_match else ""


def _normalize_rank_name(value: str) -> str:
    name = _clean_html_text(value)
    name = re.sub(r">>+$", "", name).strip()
    return name[:20]


def _qimao_rank_name(html: str) -> str:
    heading_match = re.search(
        r'<span[^>]+class=["\'][^"\']*header-txt[^"\']*["\'][^>]*>(.*?)</span>',
        html or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(heading_match.group(1)) if heading_match else ""


def _qimao_title(block: str) -> str:
    title_match = re.search(
        r'<a[^>]+class=["\'][^"\']*s-book-title[^"\']*["\'][^>]*>(.*?)</a>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(title_match.group(1)) if title_match else ""


def _qimao_tags(block: str) -> list[str]:
    info_match = re.search(
        r'<span[^>]+class=["\'][^"\']*s-book-info[^"\']*["\'][^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    if not info_match:
        return []
    link_texts = [
        _clean_html_text(item)
        for item in re.findall(r"<a[^>]*>(.*?)</a>", info_match.group(1), flags=re.I | re.S)
    ]
    tags = [item for item in link_texts[1:] if item]
    return tags[:2]


def _qimao_rank_text(block: str) -> str:
    rank_match = re.search(
        r'<span[^>]+class=["\'][^"\']*rank-number[^"\']*["\'][^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(rank_match.group(1)) if rank_match else ""


def _qimao_intro(block: str) -> str:
    intro_match = re.search(
        r'<span[^>]+class=["\'][^"\']*s-book-intro[^"\']*["\'][^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(intro_match.group(1)) if intro_match else ""


def _qimao_metric(block: str) -> str:
    metric_match = re.search(
        r'<span[^>]+class=["\'][^"\']*rank-change-num[^"\']*["\'][^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(metric_match.group(1)) if metric_match else ""


def _fanqie_title(block: str) -> str:
    title_match = re.search(
        r'<[^>]+class=["\'][^"\']*(?:book-name|book-title|title)[^"\']*["\'][^>]*>(.*?)</[^>]+>',
        block or "",
        flags=re.I | re.S,
    )
    if title_match:
        return _decode_fanqie_text(_clean_html_text(title_match.group(1)))
    page_link_match = re.search(
        r'<a[^>]+href=["\'][^"\']*/page/\d+[^"\']*["\'][^>]*>(.*?)</a>',
        block or "",
        flags=re.I | re.S,
    )
    return _decode_fanqie_text(_clean_html_text(page_link_match.group(1))) if page_link_match else ""


def _fanqie_tags(block: str, title: str) -> list[str]:
    tag_container = re.search(
        r'<(?P<tag>div|p)[^>]+class=["\'][^"\']*(?:tag|category|label)[^"\']*["\'][^>]*>(.*?)</(?P=tag)>',
        block or "",
        flags=re.I | re.S,
    )
    if not tag_container:
        return []
    tag_html = tag_container.group(2)
    raw_items = re.findall(r"<(?:span|a)[^>]*>(.*?)</(?:span|a)>", tag_html, flags=re.I | re.S)
    stop_words = {"连载", "连载中", "完结", "已完结", "作者", title}
    tags: list[str] = []
    for raw_item in raw_items:
        item = _decode_fanqie_text(_clean_html_text(raw_item))
        if not item or item in stop_words or item in tags:
            continue
        if len(item) > 12:
            continue
        tags.append(item)
    return tags[:3]


def _fanqie_summary(block: str) -> str:
    summary_match = re.search(
        r'<(?P<tag>div|p)[^>]+class=["\'][^"\']*(?:book-desc|desc|intro|abstract)[^"\']*["\'][^>]*>(.*?)</(?P=tag)>',
        block or "",
        flags=re.I | re.S,
    )
    return _decode_fanqie_text(_clean_html_text(summary_match.group(2))) if summary_match else ""


def _decode_fanqie_text(text: str) -> str:
    if not text:
        return ""
    return "".join(_FANQIE_TEXT_FONT_MAP.get(str(ord(char)), char) for char in text)


def _tencent_rank_text(block: str) -> str:
    rank_match = re.search(r"<sub[^>]*>(.*?)</sub>", block or "", flags=re.I | re.S)
    rank = _clean_html_text(rank_match.group(1)) if rank_match else ""
    return rank or "?"


def _nearest_tencent_rank_title(html: str, offset: int) -> str:
    headings = list(
        re.finditer(
            r'<h3[^>]+class=["\'][^"\']*ran-rank-title[^"\']*["\'][^>]*>(.*?)</h3>',
            html[:offset],
            flags=re.I | re.S,
        )
    )
    if not headings:
        return ""
    return _clean_html_text(headings[-1].group(1))


def _tencent_rank_metric(block: str) -> str:
    metric_match = re.search(
        r'<span[^>]+class=["\'][^"\']*mod-rank-num[^"\']*["\'][^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(metric_match.group(1)) if metric_match else ""


def _nearest_kuaikan_rank_title(html: str, offset: int) -> str:
    headings = list(
        re.finditer(
            r'<h3[^>]+class=["\'][^"\']*title[^"\']*["\'][^>]*>(.*?)</h3>',
            html[:offset],
            flags=re.I | re.S,
        )
    )
    if not headings:
        return ""
    name = _clean_html_text(headings[-1].group(1))
    return name.replace("更多", "").strip()[:20]


def _kuaikan_title(block: str) -> str:
    normal_match = re.search(
        r'<span[^>]+class=["\'][^"\']*title[^"\']*["\'][^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    if normal_match:
        return _clean_html_text(normal_match.group(1))
    hover_match = re.search(
        r'<div[^>]+class=["\'][^"\']*title[^"\']*["\'][^>]*>.*?<span[^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(hover_match.group(1)) if hover_match else ""


def _kuaikan_rank_text(block: str) -> str:
    rank_match = re.search(
        r'<span[^>]+class=["\'][^"\']*top[^"\']*["\'][^>]*>(.*?)</span>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(rank_match.group(1)) if rank_match else ""


def _kuaikan_author(block: str) -> str:
    author_match = re.search(
        r'<(?:span|p)[^>]+class=["\'][^"\']*author[^"\']*["\'][^>]*>(.*?)</(?:span|p)>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(author_match.group(1)) if author_match else ""


def _kuaikan_description(block: str) -> str:
    description_match = re.search(
        r'<p[^>]+class=["\'][^"\']*description[^"\']*["\'][^>]*>(.*?)</p>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(description_match.group(1)) if description_match else ""


def _kuaikan_update(block: str) -> str:
    update_match = re.search(
        r'<a[^>]+class=["\'][^"\']*update[^"\']*["\'][^>]*>(.*?)</a>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(update_match.group(1)) if update_match else ""


def _qidian_metadata(block: str) -> list[str]:
    author_match = re.search(
        r'<p[^>]+class=["\'][^"\']*author[^"\']*["\'][^>]*>(.*?)</p>',
        block or "",
        flags=re.I | re.S,
    )
    if not author_match:
        return []
    link_texts = [
        _clean_html_text(item)
        for item in re.findall(r"<a[^>]*>(.*?)</a>", author_match.group(1), flags=re.I | re.S)
    ]
    metadata = [item for item in link_texts[1:] if item]
    return metadata[:2]


def _qidian_intro(block: str) -> str:
    intro_match = re.search(
        r'<p[^>]+class=["\'][^"\']*intro[^"\']*["\'][^>]*>(.*?)</p>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(intro_match.group(1)) if intro_match else ""


def _nearest_qidian_mobile_rank_title(html: str, offset: int) -> str:
    headings = list(
        re.finditer(
            r'<div[^>]+class=["\'][^"\']*_rankTitle_[^"\']*["\'][^>]*>.*?<span[^>]*>(.*?)</span>',
            html[:offset],
            flags=re.I | re.S,
        )
    )
    if not headings:
        return ""
    return _clean_html_text(headings[-1].group(1))


def _qidian_mobile_rank_text(block: str) -> str:
    rank_match = re.search(
        r'<div[^>]+class=["\'][^"\']*_ranking_[^"\']*["\'][^>]*>(.*?)</div>',
        block or "",
        flags=re.I | re.S,
    )
    return _clean_html_text(rank_match.group(1)) if rank_match else ""


def _qidian_mobile_metadata(block: str) -> list[str]:
    subtitle_match = re.search(r"<p[^>]*>(.*?)</p>", block or "", flags=re.I | re.S)
    subtitle = _clean_html_text(subtitle_match.group(1)) if subtitle_match else ""
    parts = [part.strip() for part in subtitle.split("·") if part.strip()]
    metadata = [part for part in parts[1:] if not re.search(r"\d", part)]
    return metadata[:2]


def _clean_html_text(value: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", "", value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _is_signal_title(title: str) -> bool:
    if not title or len(title) < 2 or len(title) > 40:
        return False
    noise = ["排行榜", "登录", "注册", "更多", "首页", "客户端", "App", "APP"]
    return not any(word in title for word in noise)


def _summary_for_collected_title(title: str, lines: list[str]) -> str:
    for index, line in enumerate(lines):
        if title in line:
            context = [line]
            context.extend(lines[index + 1:index + 3])
            return "；".join(item for item in context if item)[:240]
    return ""
