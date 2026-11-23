"""Validate a Tauri updater manifest before its GitHub Release is published."""

from __future__ import annotations

import argparse
import json
import re
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
    if not windows_entries or "windows-x86_64" not in platforms:
        fail("windows-x86_64 platform is missing")

    signatures: set[str] = set()
    urls: set[str] = set()
    expected_download_path = f"/releases/download/{args.tag}/{args.installer}"
    api_asset_path = re.compile(r"^/repos/shenminglinyi/PlotPilot/releases/assets/\d+$")

    for platform_name, update in windows_entries:
        if not isinstance(update, dict):
            fail(f"{platform_name} must be an object")

        signature = update.get("signature")
        if not isinstance(signature, str) or not signature.strip():
            fail(f"{platform_name}.signature is missing")
        signatures.add(signature)

        url = update.get("url")
        if not isinstance(url, str):
            fail(f"{platform_name}.url is missing")
        urls.add(url)

        parsed_url = urlparse(url)
        is_public_download = (
            parsed_url.scheme == "https"
            and parsed_url.hostname == "github.com"
            and unquote(parsed_url.path).endswith(expected_download_path)
        )
        is_github_asset_api = (
            parsed_url.scheme == "https"
            and parsed_url.hostname == "api.github.com"
            and api_asset_path.fullmatch(parsed_url.path) is not None
        )
        if not (is_public_download or is_github_asset_api):
            fail(f"{platform_name}.url is not a valid GitHub Release asset URL")

    if len(signatures) != 1 or len(urls) != 1:
        fail("Windows platform aliases must reference the same signed installer")

    names = ", ".join(name for name, _ in windows_entries)
    print(f"updater manifest {args.version} is valid for {names}")


if __name__ == "__main__":
    main()
