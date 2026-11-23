"""Build a deterministic multi-platform Tauri updater manifest from release assets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def fail(message: str) -> None:
    raise SystemExit(f"cannot build updater manifest: {message}")


def one(paths: list[Path], label: str) -> Path:
    if len(paths) != 1:
        fail(f"expected exactly one {label}, found {len(paths)}")
    return paths[0]


def architecture(path: Path) -> str | None:
    name = path.name.lower()
    if "aarch64" in name or "arm64" in name:
        return "aarch64"
    if "x86_64" in name or "x64" in name:
        return "x86_64"
    return None


def signed_entry(asset: Path, *, repository: str, tag: str) -> dict[str, str]:
    signature_path = asset.with_name(asset.name + ".sig")
    try:
        signature = signature_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        fail(str(exc))
    if not signature:
        fail(f"signature is empty: {signature_path.name}")
    url = (
        f"https://github.com/{repository}/releases/download/"
        f"{quote(tag, safe='')}/{quote(asset.name, safe='')}"
    )
    return {"signature": signature, "url": url}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    repository = args.repository.strip("/")
    if repository.count("/") != 1:
        fail("repository must have the form owner/name")
    if not args.assets_dir.is_dir():
        fail(f"assets directory does not exist: {args.assets_dir}")

    installer = one(sorted(args.assets_dir.glob("*.exe")), "Windows installer")
    mac_archives = sorted(args.assets_dir.glob("*.app.tar.gz"))
    mac_by_arch: dict[str, Path] = {}
    for archive in mac_archives:
        arch = architecture(archive)
        if arch is None:
            fail(f"cannot determine architecture from {archive.name}")
        if arch in mac_by_arch:
            fail(f"multiple macOS updater archives for {arch}")
        mac_by_arch[arch] = archive
    if set(mac_by_arch) != {"aarch64", "x86_64"}:
        fail("both aarch64 and x86_64 macOS updater archives are required")

    dmgs = sorted(args.assets_dir.glob("*.dmg"))
    dmg_arches = {architecture(path) for path in dmgs}
    if dmg_arches != {"aarch64", "x86_64"} or len(dmgs) != 2:
        fail("both aarch64 and x86_64 macOS DMG installers are required")

    windows = signed_entry(installer, repository=repository, tag=args.tag)
    mac_arm = signed_entry(mac_by_arch["aarch64"], repository=repository, tag=args.tag)
    mac_intel = signed_entry(mac_by_arch["x86_64"], repository=repository, tag=args.tag)
    manifest = {
        "version": args.version,
        "notes": args.notes or f"PlotPilot desktop release {args.tag}.",
        "pub_date": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        "platforms": {
            "windows-x86_64": windows,
            "windows-x86_64-nsis": windows,
            "darwin-aarch64": mac_arm,
            "darwin-aarch64-app": mac_arm,
            "darwin-x86_64": mac_intel,
            "darwin-x86_64-app": mac_intel,
        },
    }
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote updater manifest for {', '.join(manifest['platforms'])}")


if __name__ == "__main__":
    main()
