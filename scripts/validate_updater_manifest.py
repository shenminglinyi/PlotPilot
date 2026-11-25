"""Validate the final multi-platform Tauri updater manifest and signatures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


REQUIRED_PLATFORMS = {
    "windows-x86_64",
    "windows-x86_64-nsis",
    "darwin-aarch64",
    "darwin-aarch64-app",
    "darwin-x86_64",
    "darwin-x86_64-app",
}


def fail(message: str) -> None:
    raise SystemExit(f"invalid updater manifest: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))
    if manifest.get("version") != args.version:
        fail(f"version must be {args.version!r}")

    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        fail("platforms must be an object")
    missing = REQUIRED_PLATFORMS - set(platforms)
    if missing:
        fail(f"required platforms are missing: {', '.join(sorted(missing))}")

    expected_prefix = f"/{args.repository.strip('/')}/releases/download/{args.tag}/"
    resolved: dict[str, tuple[str, str]] = {}
    for platform in sorted(REQUIRED_PLATFORMS):
        entry = platforms[platform]
        if not isinstance(entry, dict):
            fail(f"{platform} must be an object")
        signature = entry.get("signature")
        url = entry.get("url")
        if not isinstance(signature, str) or not signature.strip():
            fail(f"{platform}.signature is missing")
        if not isinstance(url, str):
            fail(f"{platform}.url is missing")

        parsed = urlparse(url)
        path = unquote(parsed.path)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            fail(f"{platform}.url must use public GitHub HTTPS downloads")
        if not path.startswith(expected_prefix):
            fail(f"{platform}.url does not point to {args.tag}")
        asset_name = Path(path).name
        asset = args.assets_dir / asset_name
        signature_file = args.assets_dir / f"{asset_name}.sig"
        if not asset.is_file():
            fail(f"asset is missing: {asset_name}")
        try:
            expected_signature = signature_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            fail(str(exc))
        if signature != expected_signature:
            fail(f"{platform}.signature does not match {signature_file.name}")
        resolved[platform] = (asset_name, signature)

    for aliases in (
        ("windows-x86_64", "windows-x86_64-nsis"),
        ("darwin-aarch64", "darwin-aarch64-app"),
        ("darwin-x86_64", "darwin-x86_64-app"),
    ):
        if len({resolved[name] for name in aliases}) != 1:
            fail(f"platform aliases do not reference the same artifact: {aliases}")

    print(f"updater manifest {args.version} is valid for {', '.join(sorted(REQUIRED_PLATFORMS))}")


if __name__ == "__main__":
    main()
