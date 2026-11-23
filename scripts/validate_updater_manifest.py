"""Validate a Tauri updater manifest before its GitHub Release is published."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


def fail(message: str) -> None:
    raise SystemExit(f"invalid updater manifest: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--installer", required=True)
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))

    if manifest.get("version") != args.version:
        fail(f"version must be {args.version!r}")

    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        fail("platforms must be a non-empty object")

    windows_entries = [
        (name, entry)
        for name, entry in platforms.items()
        if isinstance(name, str) and name.startswith("windows-")
    ]
    if len(windows_entries) != 1:
        fail(f"expected one Windows platform, found {len(windows_entries)}")

    platform_name, update = windows_entries[0]
    if not isinstance(update, dict):
        fail(f"{platform_name} must be an object")

    signature = update.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        fail(f"{platform_name}.signature is missing")

    url = update.get("url")
    if not isinstance(url, str):
        fail(f"{platform_name}.url is missing")
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "github.com":
        fail(f"{platform_name}.url must use GitHub Releases over HTTPS")

    expected_path = f"/releases/download/{args.tag}/{args.installer}"
    if not unquote(parsed_url.path).endswith(expected_path):
        fail(f"{platform_name}.url does not reference {expected_path!r}")

    print(f"updater manifest {args.version} is valid for {platform_name}")


if __name__ == "__main__":
    main()
