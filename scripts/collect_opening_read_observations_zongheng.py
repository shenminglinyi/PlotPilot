"""Collect Zongheng opening observations without persisting chapter text."""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_SOURCES = ROOT / "shared" / "taxonomy" / "sources" / "genre_taxonomy_sources_2026-05-31.json"
OUTPUT_DIR = ROOT / "data" / "genre_intelligence"
OUTPUT_JSON = OUTPUT_DIR / "opening_read_observations_zongheng_2026-05-31.json"

USER_AGENT = "Mozilla/5.0"


@dataclass(frozen=True)
class ZonghengTarget:
    category_id: str
    category_name: str
    source_url: str


def fetch_text(url: str, *, delay_seconds: float) -> str:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.zongheng.com/",
        },
    )
    with urlopen(request, timeout=30) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        content_type = response.headers.get("Content-Type", "")
    charset_match = re.search(r"charset=([\w-]+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    return raw.decode(charset, "replace")


def clean_text(value: str) -> str:
    value = re.sub(r"<.*?>", "", value, flags=re.S)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def load_targets(limit_categories: int, category_offset: int) -> list[ZonghengTarget]:
    data = json.loads(TAXONOMY_SOURCES.read_text(encoding="utf-8"))
    source = next((item for item in data.get("sources", []) if item.get("source") == "zongheng_mobile"), None)
    targets: list[ZonghengTarget] = []
    if not source:
        return targets
    for category in source.get("primary_categories", []):
        url = category.get("source_url", "")
        match = re.search(r"cateFineId=(\d+)", url)
        if not match:
            continue
        category_id = match.group(1)
        targets.append(
            ZonghengTarget(
                category_id=category_id,
                category_name=category.get("name", ""),
                source_url=f"https://book.zongheng.com/store/c{category_id}/c0/b0/u0/p1/v9/s9/t0/u0/i1/ALL.html",
            )
        )
    return targets[max(category_offset, 0) : max(category_offset, 0) + limit_categories]


def collect_books(target: ZonghengTarget, *, max_books: int, pages: int, delay_seconds: float) -> list[dict[str, Any]]:
    books: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        page_url = target.source_url.replace("/p1/", f"/p{page}/")
        text = fetch_text(page_url, delay_seconds=delay_seconds)
        for match in re.finditer(r'<div class="bookbox [^"]+">(?P<body>.*?)</div>\s*</div>\s*</div>', text, re.S):
            body = match.group("body")
            book_match = re.search(
                r'<div class="bookname">\s*<a href="https://book\.zongheng\.com/book/(?P<book_id>\d+)\.html"[^>]*>(?P<title>.*?)</a>',
                body,
                re.S,
            )
            if not book_match:
                continue
            book_id = book_match.group("book_id")
            if book_id in seen:
                continue
            seen.add(book_id)
            links = re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', body, re.S)
            author = ""
            category = ""
            latest_chapter_url = ""
            latest_chapter_title = ""
            for href, label_html in links:
                label = clean_text(label_html)
                if "home.zongheng.com" in href and not author:
                    author = label
                elif "category/" in href and not category:
                    category = label
                elif "/chapter/" in href:
                    latest_chapter_url = normalize_chapter_url(href)
                    latest_chapter_title = re.sub(r"^最新章节：", "", label)
            books.append(
                {
                    "book_id": book_id,
                    "title": clean_text(book_match.group("title")),
                    "author": author,
                    "category": category,
                    "book_url": f"https://book.zongheng.com/book/{book_id}.html",
                    "latest_chapter_url": latest_chapter_url,
                    "latest_chapter_title": latest_chapter_title,
                    "rank_in_source": len(books) + 1,
                }
            )
            if len(books) >= max_books:
                return books
    return books


def normalize_chapter_url(url: str) -> str:
    url = html.unescape(url).split("?")[0]
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://book.zongheng.com" + url
    return url.replace("https://read.zongheng.com/", "https://book.zongheng.com/")


def first_chapter_url(book: dict[str, Any], *, delay_seconds: float) -> str:
    text = fetch_text(book["book_url"], delay_seconds=delay_seconds)
    match = re.search(
        r'<a href="(?P<href>(?://read\.zongheng\.com|https://book\.zongheng\.com)?/chapter/'
        + re.escape(book["book_id"])
        + r'/\d+\.html)"[^>]*>\s*立即阅读\s*</a>',
        text,
        re.S,
    )
    if match:
        return normalize_chapter_url(match.group("href"))
    hrefs = re.findall(r'href="([^"]*/chapter/' + re.escape(book["book_id"]) + r'/\d+\.html[^"]*)"', text)
    if hrefs:
        return normalize_chapter_url(hrefs[-1])
    return ""


def read_opening(book: dict[str, Any], *, max_chapters: int, delay_seconds: float) -> dict[str, Any]:
    result = {
        "book_id": book["book_id"],
        "title": book["title"],
        "author": book.get("author", ""),
        "category": book.get("category", ""),
        "book_url": book["book_url"],
        "chapters_read": [],
        "read_error": None,
    }
    start_url = first_chapter_url(book, delay_seconds=delay_seconds)
    if not start_url:
        result["read_error"] = "missing_first_chapter_url"
        return result
    chapter_url = start_url
    seen: set[str] = set()
    for _ in range(max_chapters):
        if not chapter_url or chapter_url in seen:
            break
        seen.add(chapter_url)
        try:
            text = fetch_text(chapter_url, delay_seconds=delay_seconds)
            observation = observe_chapter(text, chapter_url)
            result["chapters_read"].append(observation)
            chapter_url = next_chapter_url(text, chapter_url)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            result["chapters_read"].append(
                {
                    "chapter_url": chapter_url,
                    "read_error": f"{type(exc).__name__}: {exc}",
                }
            )
            break
    return result


def next_chapter_url(text: str, current_url: str) -> str:
    match = re.search(
        r'<a[^>]+href="(?P<href>[^"]*/chapter/\d+/\d+\.html(?:\?[^"]*)?)"[^>]*>\s*下一章\s*</a>',
        text,
    )
    if not match:
        return ""
    next_url = normalize_chapter_url(match.group("href"))
    return "" if next_url == current_url else next_url


def observe_chapter(text: str, chapter_url: str) -> dict[str, Any]:
    title_match = re.search(r"<title>(.*?)</title>", text, re.S)
    title = clean_text(title_match.group(1)) if title_match else ""
    content_match = re.search(r'<div class="content"[^>]*>(?P<body>.*?)</div>', text, re.S)
    body_html = content_match.group("body") if content_match else ""
    transient_text = clean_text(body_html)
    paragraphs = [clean_text(item) for item in re.findall(r"<p>(.*?)</p>", body_html, re.S)]
    paragraphs = [item for item in paragraphs if item]
    char_count = len(re.sub(r"\s+", "", transient_text))
    dialogue_marks = transient_text.count("“") + transient_text.count("”")
    return {
        "chapter_url": chapter_url,
        "chapter_title": re.sub(r"_.*$", "", title),
        "char_count_read": char_count,
        "paragraph_count": len(paragraphs),
        "dialogue_mark_count": dialogue_marks,
        "dialogue_density": round(dialogue_marks / max(char_count, 1), 4),
        "action_signal_count": len(re.findall(r"[打杀冲逃追砸撞跪哭喊笑怒吼]", transient_text)),
        "sensory_signal_count": len(re.findall(r"[血痛冷热雾雨风声味光暗黑红白]", transient_text)),
        "conflict_signal_count": len(re.findall(r"[死杀仇敌恶危怒辱逼抢骗罪罚]", transient_text)),
        "last_sentence_hook_mark": bool(paragraphs and re.search(r"[？?！!。]$", paragraphs[-1])),
        "has_system_bracket": "【" in transient_text and "】" in transient_text,
        "has_opening_dialogue": bool(paragraphs and "“" in paragraphs[0]),
        "read_error": None,
    }


def collect(args: argparse.Namespace) -> dict[str, Any]:
    targets = load_targets(args.max_categories, args.category_offset)
    observations: list[dict[str, Any]] = []
    for target in targets:
        target_result = {
            "source": "zongheng_store",
            "canonical_category": target.category_name,
            "secondary_category": "",
            "source_url": target.source_url,
            "books": [],
            "read_error": None,
        }
        try:
            books = collect_books(
                target,
                max_books=args.max_books,
                pages=args.pages,
                delay_seconds=args.delay_seconds,
            )
            for book in books:
                try:
                    target_result["books"].append(
                        read_opening(book, max_chapters=args.max_chapters, delay_seconds=args.delay_seconds)
                    )
                except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                    target_result["books"].append(
                        {
                            "book_id": book.get("book_id", ""),
                            "title": book.get("title", ""),
                            "book_url": book.get("book_url", ""),
                            "chapters_read": [],
                            "read_error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            target_result["read_error"] = f"{type(exc).__name__}: {exc}"
        observations.append(target_result)
    return {
        "schema_kind": "plotpilot.opening_read_observations",
        "schema_version": 1,
        "source": "zongheng_store",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source_policy": "transient_read_only_no_chapter_body_persisted",
        "limits": {
            "category_offset": args.category_offset,
            "max_categories": args.max_categories,
            "max_books": args.max_books,
            "max_chapters": args.max_chapters,
            "pages": args.pages,
            "delay_seconds": args.delay_seconds,
        },
        "targets": observations,
    }


def merge_existing(existing: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    def target_score(target: dict[str, Any]) -> tuple[int, int, int, int]:
        books = target.get("books", [])
        valid_chapters = sum(
            1
            for book in books
            for chapter in book.get("chapters_read", [])
            if not chapter.get("read_error")
        )
        book_count = len(books)
        error_count = int(bool(target.get("read_error"))) + sum(
            int(bool(book.get("read_error"))) for book in books
        ) + sum(
            int(bool(chapter.get("read_error")))
            for book in books
            for chapter in book.get("chapters_read", [])
        )
        return (valid_chapters, book_count, -error_count, 0 if target.get("read_error") else 1)

    merged_targets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for source in (existing, current):
        for target in source.get("targets", []):
            key = (
                target.get("source", ""),
                target.get("canonical_category", ""),
                target.get("source_url", ""),
            )
            old = merged_targets.get(key)
            if old is None or target_score(target) >= target_score(old):
                merged_targets[key] = target
    merged = dict(current)
    previous_runs = existing.get("collection_runs", [])
    if not isinstance(previous_runs, list):
        previous_runs = []
    merged["collection_runs"] = previous_runs + [
        {
            "collected_at": current.get("collected_at"),
            "limits": current.get("limits", {}),
            "target_count": len(current.get("targets", [])),
        }
    ]
    merged["targets"] = list(merged_targets.values())
    merged["merged_at"] = datetime.now(timezone.utc).isoformat()
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纵横源只读采集网文开篇观察，不保存正文。")
    parser.add_argument("--category-offset", type=int, default=0)
    parser.add_argument("--max-categories", type=int, default=8)
    parser.add_argument("--max-books", type=int, default=4)
    parser.add_argument("--max-chapters", type=int, default=10)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    parser.add_argument("--output", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--merge-existing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = collect(args)
    if args.merge_existing and args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        result = merge_existing(existing, result)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    book_count = sum(len(target["books"]) for target in result["targets"])
    chapter_count = sum(len(book["chapters_read"]) for target in result["targets"] for book in target["books"])
    print(f"纵横只读采集完成：分类 {len(result['targets'])} 个，作品 {book_count} 本，章节 {chapter_count} 章。")
    print(f"已保存非正文观察：{args.output}")


if __name__ == "__main__":
    main()
