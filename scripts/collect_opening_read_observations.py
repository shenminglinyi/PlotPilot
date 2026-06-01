"""Read web-novel openings transiently and save non-text observations.

This collector is designed for market-structure research:
- It may fetch public category, book and chapter pages.
- It does not persist chapter body text.
- It only stores metadata and numeric / boolean observations that can later be
  mapped into CPMS / Variable Hub variables.
"""

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
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
MARKET_TAXONOMY = ROOT / "shared" / "taxonomy" / "genre_market_cn_v1.yaml"
OUTPUT_DIR = ROOT / "data" / "genre_intelligence"
OUTPUT_JSON = OUTPUT_DIR / "opening_read_observations_2026-05-31.json"

USER_AGENT = "Mozilla/5.0"
QIDIAN_HOST = "https://m.qidian.com"


@dataclass(frozen=True)
class ReadTarget:
    canonical_category: str
    secondary_category: str
    source_url: str


def fetch_text(url: str, *, delay_seconds: float) -> str:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
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


def absolutize_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return QIDIAN_HOST + url
    return url


def clean_label(value: str) -> str:
    value = re.sub(r"<.*?>", "", value, flags=re.S)
    value = html.unescape(value)
    return re.sub(r"\s+", "", value).strip()


def extract_page_context(text: str) -> dict[str, Any]:
    match = re.search(
        r'<script id="vite-plugin-ssr_pageContext" type="application/json">(.*?)</script>',
        text,
        re.S,
    )
    if not match:
        return {}
    payload = html.unescape(match.group(1))
    return json.loads(payload)


def page_data(context: dict[str, Any]) -> dict[str, Any]:
    return (
        context.get("pageContext", {})
        .get("pageProps", {})
        .get("pageData", {})
    )


def load_qidian_targets(limit_categories: int, category_offset: int) -> list[ReadTarget]:
    data = yaml.safe_load(MARKET_TAXONOMY.read_text(encoding="utf-8"))
    all_targets: list[ReadTarget] = []
    for category in data.get("categories", []):
        canonical = category.get("canonical_name", "")
        for secondary in category.get("secondary_categories", []):
            urls = [
                url
                for url in secondary.get("source_urls", [])
                if "m.qidian.com/category/" in url
            ]
            if not urls:
                continue
            all_targets.append(
                ReadTarget(
                    canonical_category=canonical,
                    secondary_category=secondary.get("name", ""),
                    source_url=urls[0],
                )
            )
    if category_offset < 0:
        category_offset = 0
    return all_targets[category_offset : category_offset + limit_categories]


def collect_books_from_category(target: ReadTarget, *, max_books: int, delay_seconds: float) -> list[dict[str, Any]]:
    text = fetch_text(target.source_url, delay_seconds=delay_seconds)
    context = extract_page_context(text)
    records = page_data(context).get("list", {}).get("records", [])
    books: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, record in enumerate(records, start=1):
        book_id = str(record.get("bid") or "")
        if not book_id or book_id in seen:
            continue
        seen.add(book_id)
        books.append(
            {
                "book_id": book_id,
                "title": clean_label(str(record.get("bName") or "")),
                "author": clean_label(str(record.get("bAuth") or "")),
                "rank_in_page": rank,
                "book_url": f"{QIDIAN_HOST}/book/{book_id}/",
                "category_from_list": clean_label(str(record.get("cat") or "")),
                "status_from_list": clean_label(str(record.get("state") or "")),
                "words_from_list": clean_label(str(record.get("cnt") or "")),
            }
        )
        if len(books) >= max_books:
            return books

    pattern = re.compile(
        r'<a class="[^"]*auto-click-tr[^"]*" href="(?P<href>//m\.qidian\.com/book/(?P<book_id>\d+)/)"'
        r' title="(?P<title>[^"]+)"[^>]*data-rid="(?P<rank>\d+)"',
        re.S,
    )
    for match in pattern.finditer(text):
        book_id = match.group("book_id")
        if book_id in seen:
            continue
        seen.add(book_id)
        title = clean_label(match.group("title"))
        title = re.sub(r"(最新章节在线阅读|在线阅读)$", "", title)
        books.append(
            {
                "book_id": book_id,
                "title": title,
                "rank_in_page": int(match.group("rank")),
                "book_url": absolutize_url(match.group("href")),
            }
        )
        if len(books) >= max_books:
            break
    return books


def read_book_opening(book: dict[str, Any], *, max_chapters: int, delay_seconds: float) -> dict[str, Any]:
    book_text = fetch_text(book["book_url"], delay_seconds=delay_seconds)
    context = extract_page_context(book_text)
    data = page_data(context)
    book_info = data.get("bookInfo", {})
    chapter_content_info = data.get("chapterContentInfo", {})
    first_chapter_id = (
        data.get("firstChapterId")
        or book_info.get("firstChapterId")
        or chapter_content_info.get("firstChapterId")
    )
    first_chapter_title = (
        data.get("firstChapterT")
        or chapter_content_info.get("firstChapterT")
        or ""
    )

    result = {
        "book_id": book["book_id"],
        "title": book["title"],
        "author": book_info.get("authorName", ""),
        "channel": book_info.get("chanName", ""),
        "subcategory": book_info.get("subCateName", ""),
        "words_total": book_info.get("wordsCnt", ""),
        "collect_count": book_info.get("collect", ""),
        "book_url": book["book_url"],
        "first_chapter_id": first_chapter_id,
        "first_chapter_title": first_chapter_title,
        "chapters_read": [],
        "read_error": None,
    }
    if not first_chapter_id:
        result["read_error"] = "missing_first_chapter_id"
        return result

    next_chapter_id: int | str | None = first_chapter_id
    seen_chapters: set[str] = set()
    for _ in range(max_chapters):
        if not next_chapter_id or str(next_chapter_id) in seen_chapters or int(next_chapter_id) <= 0:
            break
        seen_chapters.add(str(next_chapter_id))
        chapter_url = f"{QIDIAN_HOST}/chapter/{book['book_id']}/{next_chapter_id}/"
        try:
            chapter_text = fetch_text(chapter_url, delay_seconds=delay_seconds)
            chapter_context = extract_page_context(chapter_text)
            chapter_data = page_data(chapter_context)
            chapter_info = chapter_data.get("chapterInfo", {})
            body = chapter_info.get("content", "")
            observation = observe_chapter(
                body=body,
                chapter_id=str(next_chapter_id),
                chapter_title=(
                    chapter_info.get("chapterName", "")
                    or chapter_info.get("title", "")
                    or chapter_info.get("chapterTitle", "")
                    or chapter_info.get("cN", "")
                ),
                chapter_url=chapter_url,
                words_count=chapter_info.get("wordsCount", 0),
            )
            result["chapters_read"].append(observation)
            next_chapter_id = chapter_info.get("next")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
            result["chapters_read"].append(
                {
                    "chapter_id": str(next_chapter_id),
                    "chapter_url": chapter_url,
                    "read_error": f"{type(exc).__name__}: {exc}",
                }
            )
            break
    return result


def strip_body_text(body: str) -> str:
    text = html.unescape(body)
    text = re.sub(r"<p>", "\n", text)
    text = re.sub(r"<.*?>", "", text, flags=re.S)
    return text.strip()


def observe_chapter(
    *,
    body: str,
    chapter_id: str,
    chapter_title: str,
    chapter_url: str,
    words_count: int,
) -> dict[str, Any]:
    text = strip_body_text(body)
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    char_count = len(re.sub(r"\s+", "", text))
    dialogue_marks = text.count("“") + text.count("”")
    action_marks = len(re.findall(r"[打杀冲逃追砸撞跪哭喊笑怒吼]", text))
    sensory_marks = len(re.findall(r"[血痛冷热雾雨风声味光暗黑红白]", text))
    conflict_marks = len(re.findall(r"[死杀仇敌恶危怒辱逼抢骗罪罚]", text))
    hook_marks = len(re.findall(r"[？?！!。]$", paragraphs[-1] if paragraphs else ""))

    return {
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "chapter_url": chapter_url,
        "words_count_declared": words_count,
        "char_count_read": char_count,
        "paragraph_count": len(paragraphs),
        "dialogue_mark_count": dialogue_marks,
        "dialogue_density": round(dialogue_marks / max(char_count, 1), 4),
        "action_signal_count": action_marks,
        "sensory_signal_count": sensory_marks,
        "conflict_signal_count": conflict_marks,
        "last_sentence_hook_mark": hook_marks > 0,
        "has_system_bracket": "【" in text and "】" in text,
        "has_opening_dialogue": bool(paragraphs and "“" in paragraphs[0]),
        "read_error": None,
    }


def collect(args: argparse.Namespace) -> dict[str, Any]:
    targets = load_qidian_targets(args.max_categories, args.category_offset)
    observations: list[dict[str, Any]] = []
    for target in targets:
        target_result = {
            "canonical_category": target.canonical_category,
            "secondary_category": target.secondary_category,
            "source_url": target.source_url,
            "books": [],
            "read_error": None,
        }
        try:
            books = collect_books_from_category(
                target,
                max_books=args.max_books,
                delay_seconds=args.delay_seconds,
            )
            for book in books:
                try:
                    target_result["books"].append(
                        read_book_opening(
                            book,
                            max_chapters=args.max_chapters,
                            delay_seconds=args.delay_seconds,
                        )
                    )
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
                    target_result["books"].append(
                        {
                            "book_id": book.get("book_id", ""),
                            "title": book.get("title", ""),
                            "book_url": book.get("book_url", ""),
                            "chapters_read": [],
                            "read_error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
            target_result["read_error"] = f"{type(exc).__name__}: {exc}"
        observations.append(target_result)

    return {
        "schema_kind": "plotpilot.opening_read_observations",
        "schema_version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source_policy": "transient_read_only_no_chapter_body_persisted",
        "limits": {
            "category_offset": args.category_offset,
            "max_categories": args.max_categories,
            "max_books": args.max_books,
            "max_chapters": args.max_chapters,
            "delay_seconds": args.delay_seconds,
        },
        "targets": observations,
    }


def merge_existing(existing: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    def target_score(target: dict[str, Any]) -> tuple[int, int, int, int]:
        books = target.get("books", [])
        chapter_count = sum(len(book.get("chapters_read", [])) for book in books)
        book_count = len(books)
        error_count = int(bool(target.get("read_error"))) + sum(
            int(bool(book.get("read_error"))) for book in books
        )
        return (chapter_count, book_count, -error_count, 0 if target.get("read_error") else 1)

    merged_targets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for source in (existing, current):
        for target in source.get("targets", []):
            key = (
                target.get("canonical_category", ""),
                target.get("secondary_category", ""),
                target.get("source_url", ""),
            )
            previous = merged_targets.get(key)
            if previous is None or target_score(target) >= target_score(previous):
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
    parser = argparse.ArgumentParser(description="只读采集网文开篇观察，不保存正文。")
    parser.add_argument("--category-offset", type=int, default=0)
    parser.add_argument("--max-categories", type=int, default=3)
    parser.add_argument("--max-books", type=int, default=3)
    parser.add_argument("--max-chapters", type=int, default=10)
    parser.add_argument("--delay-seconds", type=float, default=0.2)
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
    chapter_count = sum(
        len(book["chapters_read"])
        for target in result["targets"]
        for book in target["books"]
    )
    print(f"只读采集完成：分类 {len(result['targets'])} 个，作品 {book_count} 本，章节 {chapter_count} 章。")
    print(f"已保存非正文观察：{args.output}")


if __name__ == "__main__":
    main()
