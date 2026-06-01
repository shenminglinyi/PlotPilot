"""Collect public Chinese web-novel genre taxonomy snapshots.

The script intentionally collects category metadata only. It does not fetch or
persist novel chapter body text.
"""

from __future__ import annotations

import gzip
import html
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "shared" / "taxonomy" / "sources"
OUTPUT_JSON = SOURCE_DIR / "genre_taxonomy_sources_2026-05-31.json"
OUTPUT_YAML = ROOT / "shared" / "taxonomy" / "genre_market_cn_v1.yaml"
REPORT_MD = ROOT / "总结输出" / "类型分类采集与归一化报告-2026-05-31.md"
BUILTIN_TAXONOMY = ROOT / "shared" / "taxonomy" / "builtin_cn_v1.yaml"

USER_AGENT = "Mozilla/5.0"


@dataclass(frozen=True)
class SourcePage:
    source: str
    url: str
    scope: str
    note: str


SOURCES = [
    SourcePage(
        source="qidian_mobile",
        url="https://m.qidian.com/category",
        scope="男频大类和二级分类",
        note="移动端分类页直接服务大类与二级分类按钮。",
    ),
    SourcePage(
        source="zongheng_mobile",
        url="https://m.zongheng.com/category",
        scope="男频大类",
        note="移动端分类页服务大类与作品数量；该页未展开二级分类。",
    ),
    SourcePage(
        source="zongheng_store",
        url="https://book.zongheng.com/store.html",
        scope="书库大类与列表可见分类",
        note="PC 书库页服务大类导航和当前列表分类。",
    ),
    SourcePage(
        source="17k_all",
        url="https://www.17k.com/all",
        scope="男女频大类与列表可见二级分类",
        note="全站书库页服务大类；列表行可观察到部分二级分类。",
    ),
]


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=30) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        content_type = response.headers.get("Content-Type", "")
    charset_match = re.search(r"charset=([\w-]+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    return raw.decode(charset, "replace")


def clean_label(value: str) -> str:
    value = re.sub(r"<.*?>", "", value, flags=re.S)
    value = html.unescape(value)
    value = re.sub(r"\s+", "", value)
    value = value.strip("[]>：: ")
    return value


def absolutize_url(url: str, base_host: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return base_host.rstrip("/") + url
    return url


def add_category(
    bucket: dict[str, Any],
    primary: str,
    primary_url: str,
    secondary: str | None = None,
    secondary_url: str | None = None,
    source_path: str | None = None,
) -> None:
    if not primary:
        return
    primary_entry = bucket.setdefault(
        primary,
        {
            "name": primary,
            "source_url": primary_url,
            "secondary_categories": {},
        },
    )
    if secondary:
        primary_entry["secondary_categories"].setdefault(
            secondary,
            {
                "name": secondary,
                "source_url": secondary_url or primary_url,
                "source_path": source_path or primary,
            },
        )


def parse_qidian_mobile(text: str) -> list[dict[str, Any]]:
    categories: dict[str, Any] = {}
    item_pattern = re.compile(
        r'<li class="[^"]*_sortListItem[^"]*"[^>]*>(?P<body>.*?)</li>',
        re.S,
    )
    head_pattern = re.compile(
        r'<a href="(?P<href>[^"]+)"[^>]*title="(?P<title>[^"]+)小说".*?'
        r'<span>(?P<label>[^<]+)</span>',
        re.S,
    )
    sub_pattern = re.compile(
        r'<a[^>]+title="(?P<title>[^"]+)小说"[^>]+href="(?P<href>[^"]+)"[^>]*>.*?'
        r'<span class="y-button__text"><!--\[-->(?P<label>.*?)<!--\]--></span>',
        re.S,
    )
    for item in item_pattern.finditer(text):
        body = item.group("body")
        head = head_pattern.search(body)
        if not head:
            continue
        primary = clean_label(head.group("label"))
        primary_url = absolutize_url(head.group("href"), "https://m.qidian.com")
        for sub in sub_pattern.finditer(body):
            secondary = clean_label(sub.group("label"))
            add_category(
                categories,
                primary,
                primary_url,
                secondary=secondary,
                secondary_url=absolutize_url(sub.group("href"), "https://m.qidian.com"),
                source_path=f"{primary}/{secondary}",
            )
        add_category(categories, primary, primary_url)
    return finalize_categories(categories)


def parse_zongheng_mobile(text: str) -> list[dict[str, Any]]:
    categories: dict[str, Any] = {}
    pattern = re.compile(
        r'<a class="flex" href="(?P<href>[^"]*cateFineId=(?P<id>\d+)[^"]*)"[^>]*'
        r'data-sa-d=\'[^\']*catedgory_name":"(?P<label>[^"]+)"[^\']*\'',
        re.S,
    )
    for match in pattern.finditer(text):
        label = clean_label(match.group("label"))
        if label == "全部":
            continue
        add_category(
            categories,
            label,
            absolutize_url(match.group("href"), "https://m.zongheng.com"),
        )
    return finalize_categories(categories)


def parse_zongheng_store(text: str) -> list[dict[str, Any]]:
    categories: dict[str, Any] = {}
    for match in re.finditer(r'<a href="(?P<href>[^"]*/category/\d+\.html)"[^>]*>(?P<label>[^<]{1,20})</a>', text):
        label = clean_label(match.group("label"))
        if not is_probable_genre_label(label):
            continue
        add_category(
            categories,
            label,
            absolutize_url(match.group("href"), "https://www.zongheng.com"),
        )
    return finalize_categories(categories)


def parse_17k_all(text: str) -> list[dict[str, Any]]:
    categories: dict[str, Any] = {}
    primary_id_to_name: dict[str, str] = {}
    primary_pattern = re.compile(
        r'<a href="(?P<href>/all/book/(?P<gender>[23])_(?P<cat>\d+)_0_0_0_0_0_0_1\.html)"[^>]*>'
        r"(?P<label>.*?)</a>",
        re.S,
    )
    for match in primary_pattern.finditer(text):
        label = clean_label(match.group("label"))
        if label in {"男生", "女生", "全部", "不限"}:
            continue
        key = f'{match.group("gender")}_{match.group("cat")}'
        primary_id_to_name[key] = label
        add_category(categories, label, absolutize_url(match.group("href"), "https://www.17k.com"))

    child_pattern = re.compile(
        r'<a[^>]+href="(?P<href>/all/book/(?P<gender>[23])_(?P<cat>\d+)_(?P<child>\d+)[^"]*?\.html)"[^>]*>'
        r"(?P<label>.*?)</a>",
        re.S,
    )
    for match in child_pattern.finditer(text):
        child = match.group("child")
        if child == "0":
            continue
        primary = primary_id_to_name.get(f'{match.group("gender")}_{match.group("cat")}')
        secondary = clean_label(match.group("label"))
        if not primary or not secondary or not is_probable_genre_label(secondary):
            continue
        add_category(
            categories,
            primary,
            categories[primary]["source_url"],
            secondary=secondary,
            secondary_url=absolutize_url(match.group("href"), "https://www.17k.com"),
            source_path=f"{primary}/{secondary}",
        )
    return finalize_categories(categories)


def is_probable_genre_label(label: str) -> bool:
    if not label or len(label) > 12:
        return False
    deny = {"友情链接", "男生频道", "女生频道", "最新章节", "立即登录"}
    if label in deny:
        return False
    genre_chars = set("玄奇武仙都市历科幻游体军悬疑灵异言情青春现实轻小说末世同人体育军事")
    return any(char in genre_chars for char in label)


def finalize_categories(categories: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for primary in sorted(categories):
        entry = categories[primary]
        secondaries = list(entry["secondary_categories"].values())
        secondaries.sort(key=lambda item: item["name"])
        result.append(
            {
                "name": entry["name"],
                "source_url": entry["source_url"],
                "secondary_categories": secondaries,
            }
        )
    return result


def load_builtin_taxonomy() -> dict[str, set[str]]:
    data = yaml.safe_load(BUILTIN_TAXONOMY.read_text(encoding="utf-8"))
    taxonomy: dict[str, set[str]] = {}
    for root in data.get("roots", []):
        name = root.get("labels", {}).get("zh-CN")
        if not name:
            continue
        taxonomy[name] = {
            child.get("labels", {}).get("zh-CN")
            for child in root.get("children", [])
            if child.get("labels", {}).get("zh-CN")
        }
    return taxonomy


ALIASES = {
    "奇幻玄幻": "玄幻",
    "玄幻奇幻": "玄幻",
    "仙侠武侠": "仙侠",
    "武侠仙侠": "仙侠",
    "都市小说": "都市",
    "都市娱乐": "都市",
    "历史军事": "历史",
    "游戏竞技": "游戏",
    "科幻末世": "科幻",
    "悬疑推理": "悬疑",
    "悬疑小说": "悬疑",
    "悬疑灵异": "悬疑",
    "奇闻异事": "灵异",
    "轻小说": "轻小说",
    "现代言情": "言情兼容",
    "古代言情": "言情兼容",
    "幻想言情": "言情兼容",
    "浪漫青春": "言情兼容",
    "现实": "现实题材",
    "现实题材": "现实题材",
    "N次元": "轻小说",
    "N 次元": "轻小说",
    "玄幻小说": "玄幻",
    "都市小说": "都市",
    "言情小说": "言情兼容",
}


def canonicalize_primary(name: str, builtin: dict[str, set[str]]) -> str:
    return name if name in builtin else ALIASES.get(name, name)


def build_market_yaml(snapshot: dict[str, Any], builtin: dict[str, set[str]]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for source in snapshot["sources"]:
        for primary in source["primary_categories"]:
            canonical = canonicalize_primary(primary["name"], builtin)
            item = merged.setdefault(
                canonical,
                {
                    "canonical_name": canonical,
                    "platform_names": defaultdict(list),
                    "secondary_categories": {},
                },
            )
            item["platform_names"][source["source"]].append(primary["name"])
            for secondary in primary.get("secondary_categories", []):
                child = item["secondary_categories"].setdefault(
                    secondary["name"],
                    {
                        "name": secondary["name"],
                        "observed_in": [],
                        "source_urls": [],
                    },
                )
                child["observed_in"].append(source["source"])
                child["source_urls"].append(secondary["source_url"])

    normalized = []
    for canonical in sorted(merged):
        item = merged[canonical]
        platform_names = {
            source: sorted(set(names))
            for source, names in sorted(item["platform_names"].items())
        }
        secondary_categories = sorted(
            (
                {
                    "name": child["name"],
                    "observed_in": sorted(set(child["observed_in"])),
                    "status_against_builtin": (
                        "builtin_exists"
                        if child["name"] in builtin.get(canonical, set())
                        else "candidate_or_alias"
                    ),
                    "source_urls": sorted(set(child["source_urls"])),
                }
                for child in item["secondary_categories"].values()
            ),
            key=lambda child: child["name"],
        )
        normalized.append(
            {
                "canonical_name": canonical,
                "platform_names": platform_names,
                "status_against_builtin": "builtin_exists" if canonical in builtin else "candidate_primary",
                "secondary_categories": secondary_categories,
            }
        )

    return {
        "schema_kind": "plotpilot.genre_market_taxonomy",
        "schema_version": 1,
        "collected_at": snapshot["collected_at"],
        "canonical_basis": "shared/taxonomy/builtin_cn_v1.yaml",
        "copyright_policy": "只保存分类元数据；不保存章节正文。",
        "categories": normalized,
    }


def render_report(snapshot: dict[str, Any], market_yaml: dict[str, Any], builtin: dict[str, set[str]]) -> str:
    lines: list[str] = [
        "# 类型分类采集与归一化报告（2026-05-31）",
        "",
        "## 本轮结论",
        "",
        "- 已完成公开分类页的第一轮采集，产物只包含分类元数据，不包含章节正文。",
        "- 暂不修改 `shared/taxonomy/builtin_cn_v1.yaml`，避免把平台差异直接硬塞进项目权威分类。",
        "- 建议把本轮输出作为 `GenreTaxonomy` / `GenrePromptVariables` 的市场参考层，后续再由 CPMS / Variable Hub 注入生文链路。",
        "",
        "## 采集源",
        "",
    ]
    for source in snapshot["sources"]:
        lines.append(f"- {source['source']}：{source['url']}；范围：{source['scope']}；说明：{source['note']}")
    lines += [
        "",
        "## 与项目现有 taxonomy 的归一化观察",
        "",
    ]
    for category in market_yaml["categories"]:
        secondaries = category.get("secondary_categories", [])
        existing = [item["name"] for item in secondaries if item["status_against_builtin"] == "builtin_exists"]
        candidates = [item["name"] for item in secondaries if item["status_against_builtin"] != "builtin_exists"]
        lines.append(f"### {category['canonical_name']}")
        lines.append(f"- 平台命名：{json.dumps(category['platform_names'], ensure_ascii=False)}")
        lines.append(f"- 内置一级状态：{category['status_against_builtin']}")
        lines.append(f"- 已与内置二级重合：{', '.join(existing) if existing else '暂无'}")
        lines.append(f"- 候选新增 / alias：{', '.join(candidates) if candidates else '暂无'}")
        if category["canonical_name"] in builtin:
            builtin_children = sorted(builtin[category["canonical_name"]])
            lines.append(f"- 项目当前二级：{', '.join(builtin_children) if builtin_children else '暂无'}")
        lines.append("")
    lines += [
        "## 架构建议",
        "",
        "1. 保留 `builtin_cn_v1.yaml` 作为 canonical，不让平台分类直接覆盖核心树。",
        "2. 新增市场映射层：平台分类只映射到 canonical genre / alias / market tag。",
        "3. 后续热门作品开头分析只保存结构化字段：开篇入口、主角初始状态、第一章钩子、前三章兑现、前十章追读循环、类型读者承诺、禁忌开头。",
        "4. 生文链路不要拼接硬编码分类文案，应通过 CPMS / Variable Hub 暴露 `genre.market_track`、`genre.reader_promise`、`opening.pattern_profile` 等变量。",
        "",
        "## 输出文件",
        "",
        f"- 原始采集快照：`{OUTPUT_JSON}`",
        f"- 市场归一化 YAML：`{OUTPUT_YAML}`",
        f"- 本报告：`{REPORT_MD}`",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)

    collected_sources: list[dict[str, Any]] = []
    parser_by_source = {
        "qidian_mobile": parse_qidian_mobile,
        "zongheng_mobile": parse_zongheng_mobile,
        "zongheng_store": parse_zongheng_store,
        "17k_all": parse_17k_all,
    }
    for source in SOURCES:
        try:
            text = fetch_text(source.url)
            categories = parser_by_source[source.source](text)
            error = None
        except (OSError, URLError, TimeoutError, UnicodeError, gzip.BadGzipFile) as exc:
            categories = []
            error = f"{type(exc).__name__}: {exc}"
        collected_sources.append(
            {
                "source": source.source,
                "url": source.url,
                "scope": source.scope,
                "note": source.note,
                "error": error,
                "primary_categories": categories,
            }
        )

    snapshot = {
        "schema_kind": "plotpilot.genre_taxonomy_sources",
        "schema_version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "copyright_policy": "metadata_only_no_chapter_text",
        "sources": collected_sources,
    }
    OUTPUT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    builtin = load_builtin_taxonomy()
    market_yaml = build_market_yaml(snapshot, builtin)
    OUTPUT_YAML.write_text(
        yaml.safe_dump(market_yaml, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    REPORT_MD.write_text(render_report(snapshot, market_yaml, builtin), encoding="utf-8")

    total_primary = sum(len(source["primary_categories"]) for source in collected_sources)
    total_secondary = sum(
        len(primary["secondary_categories"])
        for source in collected_sources
        for primary in source["primary_categories"]
    )
    print(f"采集完成：一级分类 {total_primary} 条，二级分类 {total_secondary} 条")
    print(f"原始快照：{OUTPUT_JSON}")
    print(f"归一化：{OUTPUT_YAML}")
    print(f"报告：{REPORT_MD}")


if __name__ == "__main__":
    main()
