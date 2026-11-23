"""Prepare and independently verify PlotPilot desktop releases.

This CLI automates deterministic checks while deliberately leaving commits, pushes,
worktree synchronization and tag creation as explicit maintainer decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "shenminglinyi/PlotPilot"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
REQUIRED_PLATFORMS = {
    "windows-x86_64",
    "windows-x86_64-nsis",
    "darwin-aarch64",
    "darwin-aarch64-app",
    "darwin-x86_64",
    "darwin-x86_64-app",
}
VERSION_MANIFESTS = (
    Path("VERSION"),
    Path("frontend/package.json"),
    Path("frontend/package-lock.json"),
    Path("frontend/src-tauri/Cargo.toml"),
    Path("frontend/src-tauri/Cargo.lock"),
    Path("frontend/src-tauri/tauri.conf.json"),
    Path("interfaces/api/settings.py"),
)


def fail(message: str) -> None:
    raise SystemExit(f"desktop release error: {message}")


def normalize_version(raw: str) -> str:
    version = raw.strip()
    if version.startswith("v"):
        version = version[1:]
    if not SEMVER.fullmatch(version):
        fail(f"invalid semantic version: {raw!r}")
    return version


def run(
    command: list[str],
    *,
    capture: bool = False,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    print("+", subprocess.list2cmdline(command), flush=True)
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )
    if result.returncode != 0:
        if capture:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
        fail(f"command failed with exit code {result.returncode}: {command[0]}")
    return result


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        fail(f"required command is not available: {name}")


def assert_version_manifests_clean() -> None:
    result = run(
        ["git", "status", "--porcelain", "--", *(str(path) for path in VERSION_MANIFESTS)],
        capture=True,
    )
    dirty = result.stdout.strip()
    if dirty:
        fail(
            "release version manifests already contain local changes; commit, stash, or "
            f"resolve them before preparing a release:\n{dirty}"
        )


def assert_remote_tag_absent(tag: str) -> None:
    result = run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], capture=True
    )
    if result.stdout.strip():
        fail(f"public tag already exists: {tag}")


def assert_signing_secrets() -> None:
    result = run(["gh", "secret", "list", "--repo", REPOSITORY], capture=True)
    names = {line.split("\t", 1)[0] for line in result.stdout.splitlines() if line.strip()}
    required = {"TAURI_SIGNING_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY_PASSWORD"}
    missing = required - names
    if missing:
        fail(f"GitHub signing secrets are missing: {', '.join(sorted(missing))}")


def prepare(version: str, *, skip_build: bool) -> None:
    for tool in ("git", "gh", "npm", "cargo"):
        require_tool(tool)
    assert_version_manifests_clean()
    assert_remote_tag_absent(f"v{version}")
    assert_signing_secrets()

    (ROOT / "VERSION").write_text(version + "\n", encoding="utf-8", newline="\n")
    run([sys.executable, "scripts/sync_release_version.py"])
    run([sys.executable, "scripts/sync_release_version.py", "--check"])
    run([sys.executable, "-m", "pytest", "tests/unit/scripts", "-q"])
    if not skip_build:
        run(["npm", "run", "build"], cwd=ROOT / "frontend")
        run(
            [
                "cargo",
                "fmt",
                "--manifest-path",
                "frontend/src-tauri/Cargo.toml",
                "--",
                "--check",
            ]
        )
        run(["cargo", "check", "--manifest-path", "frontend/src-tauri/Cargo.toml"])

    print(f"\nDesktop release {version} is prepared and locally verified.")
    print("Review the diff, commit it, synchronize the public repository, then push tag", f"v{version}.")


def request_bytes(url: str, *, method: str = "GET") -> tuple[int, str, bytes]:
    request = Request(
        url,
        method=method,
        headers={"User-Agent": "PlotPilot-release-verifier", "Cache-Control": "no-cache"},
    )
    with urlopen(request, timeout=60) as response:
        return response.status, response.headers.get_content_type(), response.read()


def validate_public_manifest(manifest: dict[str, object], version: str) -> list[str]:
    if manifest.get("version") != version:
        fail(f"public latest.json version is {manifest.get('version')!r}, expected {version!r}")
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        fail("public latest.json platforms must be an object")
    missing = REQUIRED_PLATFORMS - set(platforms)
    if missing:
        fail(f"public latest.json is missing: {', '.join(sorted(missing))}")
    urls = set()
    for platform in REQUIRED_PLATFORMS:
        entry = platforms[platform]
        if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
            fail(f"public latest.json has an invalid entry: {platform}")
        urls.add(entry["url"])
    if len(urls) != 3:
        fail(f"expected three unique updater downloads, found {len(urls)}")
    return sorted(urls)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_downloaded_asset_digests(
    assets_dir: Path, release_assets: list[object]
) -> None:
    if not release_assets:
        fail("GitHub release contains no assets")
    for raw_asset in release_assets:
        if not isinstance(raw_asset, dict):
            fail("GitHub release assets response is invalid")
        name = raw_asset.get("name")
        digest = raw_asset.get("digest")
        if not isinstance(name, str) or not isinstance(digest, str):
            fail("GitHub release asset is missing its name or digest")
        if not digest.startswith("sha256:"):
            fail(f"unsupported GitHub digest for {name}: {digest}")
        path = assets_dir / name
        if not path.is_file():
            fail(f"downloaded release asset is missing: {name}")
        actual = sha256_file(path)
        expected = digest.removeprefix("sha256:").lower()
        if actual != expected:
            fail(f"SHA-256 mismatch for {name}: {actual} != {expected}")


def verify(version: str) -> None:
    for tool in ("gh",):
        require_tool(tool)
    tag = f"v{version}"
    release_result = run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--repo",
            REPOSITORY,
            "--json",
            "isDraft,isPrerelease,publishedAt,url,assets",
        ],
        capture=True,
    )
    release = json.loads(release_result.stdout)
    if release.get("isDraft") or release.get("isPrerelease"):
        fail(f"{tag} is not a stable published release")
    release_assets = release.get("assets")
    if not isinstance(release_assets, list):
        fail("GitHub release assets response is invalid")

    with tempfile.TemporaryDirectory(prefix=f"plotpilot-{tag}-") as temp:
        assets_dir = Path(temp)
        run(
            ["gh", "release", "download", tag, "--repo", REPOSITORY, "--dir", temp]
        )
        run(
            [
                sys.executable,
                "scripts/validate_updater_manifest.py",
                "--manifest",
                str(assets_dir / "latest.json"),
                "--assets-dir",
                temp,
                "--repository",
                REPOSITORY,
                "--tag",
                tag,
                "--version",
                version,
            ]
        )
        verify_downloaded_asset_digests(assets_dir, release_assets)

    cache_buster = int(time.time() * 1000)
    latest_url = (
        f"https://github.com/{REPOSITORY}/releases/latest/download/"
        f"latest.json?verify={cache_buster}"
    )
    status, content_type, body = request_bytes(latest_url)
    if status != 200 or content_type not in {"application/json", "application/octet-stream"}:
        fail(f"public latest.json returned HTTP {status} ({content_type})")
    manifest = json.loads(body.decode("utf-8"))
    updater_urls = validate_public_manifest(manifest, version)

    dmg_urls = [
        asset.get("url")
        for asset in release_assets
        if isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and asset["name"].endswith(".dmg")
        and isinstance(asset.get("url"), str)
    ]
    if len(dmg_urls) != 2:
        fail(f"expected two DMG installers, found {len(dmg_urls)}")

    for url in [*updater_urls, *dmg_urls]:
        head_status, head_type, _ = request_bytes(url, method="HEAD")
        if head_status != 200 or head_type != "application/octet-stream":
            fail(f"asset check failed: HTTP {head_status} ({head_type}) {url}")

    print(f"\nDesktop release {tag} is published and verified.")
    print(release["url"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare", help="synchronize a new version and run local release checks"
    )
    prepare_parser.add_argument("version")
    prepare_parser.add_argument(
        "--skip-build",
        action="store_true",
        help="skip npm build and cargo checks; manifest tests still run",
    )

    verify_parser = subparsers.add_parser(
        "verify", help="verify a published GitHub release and its public downloads"
    )
    verify_parser.add_argument("version")

    args = parser.parse_args()
    version = normalize_version(args.version)
    if args.command == "prepare":
        prepare(version, skip_build=args.skip_build)
    elif args.command == "verify":
        verify(version)


if __name__ == "__main__":
    main()
