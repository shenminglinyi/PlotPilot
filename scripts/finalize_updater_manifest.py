"""Convert draft-only updater asset URLs into stable public download URLs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote


def fail(message: str) -> None:
    raise SystemExit(f"cannot finalize updater manifest: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--installer", required=True)
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))

    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        fail("platforms must be a non-empty object")

    windows_entries = {
        name: entry
        for name, entry in platforms.items()
        if isinstance(name, str) and name.startswith("windows-")
    }
    if not windows_entries:
        fail("no Windows platform entries were found")
    if any(not isinstance(entry, dict) for entry in windows_entries.values()):
        fail("every Windows platform entry must be an object")

    repository = args.repository.strip("/")
    if repository.count("/") != 1:
        fail("repository must have the form owner/name")
    public_url = (
        f"https://github.com/{repository}/releases/download/"
        f"{quote(args.tag, safe='')}/{quote(args.installer, safe='')}"
    )
    for entry in windows_entries.values():
        entry["url"] = public_url

    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"finalized updater manifest URL: {public_url}")


if __name__ == "__main__":
    main()
