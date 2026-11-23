from __future__ import annotations

import hashlib

import pytest

from scripts.release_desktop import (
    normalize_version,
    validate_public_manifest,
    verify_downloaded_asset_digests,
)


def manifest(version: str = "4.8.2") -> dict[str, object]:
    return {
        "version": version,
        "platforms": {
            "windows-x86_64": {"url": "https://example.test/windows"},
            "windows-x86_64-nsis": {"url": "https://example.test/windows"},
            "darwin-aarch64": {"url": "https://example.test/mac-arm"},
            "darwin-aarch64-app": {"url": "https://example.test/mac-arm"},
            "darwin-x86_64": {"url": "https://example.test/mac-intel"},
            "darwin-x86_64-app": {"url": "https://example.test/mac-intel"},
        },
    }


@pytest.mark.parametrize("raw", ["4.8.2", "v4.8.2", " 4.8.2 "])
def test_normalize_version(raw: str) -> None:
    assert normalize_version(raw) == "4.8.2"


@pytest.mark.parametrize("raw", ["4.8", "release-4.8.2", "v", ""])
def test_normalize_version_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(SystemExit, match="invalid semantic version"):
        normalize_version(raw)


def test_validate_public_manifest_returns_three_downloads() -> None:
    assert validate_public_manifest(manifest(), "4.8.2") == [
        "https://example.test/mac-arm",
        "https://example.test/mac-intel",
        "https://example.test/windows",
    ]


def test_validate_public_manifest_rejects_missing_platform() -> None:
    value = manifest()
    del value["platforms"]["darwin-x86_64"]  # type: ignore[index]
    with pytest.raises(SystemExit, match="darwin-x86_64"):
        validate_public_manifest(value, "4.8.2")


def test_verify_downloaded_asset_digests(tmp_path) -> None:
    content = b"signed installer"
    (tmp_path / "installer.exe").write_bytes(content)
    verify_downloaded_asset_digests(
        tmp_path,
        [
            {
                "name": "installer.exe",
                "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
            }
        ],
    )


def test_verify_downloaded_asset_digests_rejects_mismatch(tmp_path) -> None:
    (tmp_path / "installer.exe").write_bytes(b"tampered")
    with pytest.raises(SystemExit, match="SHA-256 mismatch"):
        verify_downloaded_asset_digests(
            tmp_path,
            [{"name": "installer.exe", "digest": f"sha256:{'0' * 64}"}],
        )
