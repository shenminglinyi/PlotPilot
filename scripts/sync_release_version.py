"""Synchronize PlotPilot's release version across every runtime manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def release_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        raise SystemExit(f"VERSION is not valid semantic versioning: {version!r}")
    return version


def replace_once(source: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"could not locate {label} version field")
    return updated


def expected_files(version: str) -> dict[Path, str]:
    package_path = ROOT / "frontend" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = version

    package_lock_path = ROOT / "frontend" / "package-lock.json"
    package_lock = json.loads(package_lock_path.read_text(encoding="utf-8"))
    package_lock["version"] = version
    package_lock["packages"][""]["version"] = version

    tauri_path = ROOT / "frontend" / "src-tauri" / "tauri.conf.json"
    tauri = json.loads(tauri_path.read_text(encoding="utf-8"))
    tauri["version"] = version

    cargo_path = ROOT / "frontend" / "src-tauri" / "Cargo.toml"
    cargo = cargo_path.read_text(encoding="utf-8")
    cargo = replace_once(
        cargo,
        r'^(\[package\]\r?\nname = "plotpilot"\r?\nversion = ")[^"]+("\s*)$',
        rf"\g<1>{version}\g<2>",
        "Cargo.toml",
    )

    cargo_lock_path = ROOT / "frontend" / "src-tauri" / "Cargo.lock"
    cargo_lock = cargo_lock_path.read_text(encoding="utf-8")
    cargo_lock = replace_once(
        cargo_lock,
        r'^(name = "plotpilot"\r?\nversion = ")[^"]+("\s*)$',
        rf"\g<1>{version}\g<2>",
        "Cargo.lock",
    )

    settings_path = ROOT / "interfaces" / "api" / "settings.py"
    settings = settings_path.read_text(encoding="utf-8")
    settings = replace_once(
        settings,
        r'^APP_RELEASE_VERSION = "[^"]+"$',
        f'APP_RELEASE_VERSION = "{version}"',
        "backend settings",
    )

    return {
        package_path: json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        package_lock_path: json.dumps(package_lock, ensure_ascii=False, indent=2) + "\n",
        tauri_path: json.dumps(tauri, ensure_ascii=False, indent=2) + "\n",
        cargo_path: cargo,
        cargo_lock_path: cargo_lock,
        settings_path: settings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail when manifests differ from VERSION")
    args = parser.parse_args()
    version = release_version()
    mismatches: list[str] = []

    for path, expected in expected_files(version).items():
        current = path.read_text(encoding="utf-8")
        if current == expected:
            continue
        if args.check:
            mismatches.append(path.relative_to(ROOT).as_posix())
        else:
            path.write_text(expected, encoding="utf-8", newline="\n")
            print(f"updated {path.relative_to(ROOT)} -> {version}")

    if mismatches:
        joined = "\n  - ".join(mismatches)
        raise SystemExit(f"release version drift detected:\n  - {joined}")
    print(f"release version {version} is synchronized")


if __name__ == "__main__":
    main()
