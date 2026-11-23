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
    parser.add_argument("--signature-file", type=Path, required=True)
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

    try:
        expected_signature = args.signature_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        fail(str(exc))
    if not expected_signature:
        fail("signature file is empty")

    for platform_name, update in windows_entries:
        if not isinstance(update, dict):
            fail(f"{platform_name} must be an object")

        signature = update.get("signature")
        if not isinstance(signature, str) or not signature.strip():
            fail(f"{platform_name}.signature is missing")
        if signature != expected_signature:
            fail(f"{platform_name}.signature does not match the sidecar signature")
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
        if not is_public_download:
            fail(f"{platform_name}.url is not the public GitHub Release download URL")

    if len(signatures) != 1 or len(urls) != 1:
        fail("Windows platform aliases must reference the same signed installer")

    names = ", ".join(name for name, _ in windows_entries)
    print(f"updater manifest {args.version} is valid for {names}")


if __name__ == "__main__":
    main()
