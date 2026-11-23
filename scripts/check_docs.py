"""Validate local links in tracked Markdown documentation."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)]+)\)")
EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data", "codex"}


def tracked_markdown_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md", "*.mdx"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        REPO_ROOT / entry.decode("utf-8")
        for entry in result.stdout.split(b"\0")
        if entry
    ]


def link_path(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]

    parsed = urlsplit(target)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or target.startswith("#"):
        return None
    if parsed.scheme or not parsed.path:
        return None
    return unquote(parsed.path)


def broken_links(markdown_file: Path) -> list[tuple[int, str]]:
    failures: list[tuple[int, str]] = []
    text = markdown_file.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK.finditer(text):
        relative = link_path(match.group("target"))
        if relative is None:
            continue
        candidate = (
            REPO_ROOT / relative.lstrip("/")
            if relative.startswith("/")
            else markdown_file.parent / relative
        )
        if not candidate.resolve().exists():
            line = text.count("\n", 0, match.start()) + 1
            failures.append((line, match.group("target")))
    return failures


def main() -> int:
    failures: list[str] = []
    checked = 0
    for markdown_file in tracked_markdown_files():
        if not markdown_file.exists():
            continue
        checked += 1
        for line, target in broken_links(markdown_file):
            relative_file = markdown_file.relative_to(REPO_ROOT)
            failures.append(f"{relative_file}:{line}: broken link: {target}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Documentation links OK ({checked} tracked Markdown files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
