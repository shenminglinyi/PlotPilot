from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def create_signed_asset(directory: Path, name: str, signature: str) -> None:
    (directory / name).write_bytes(f"asset:{name}".encode())
    (directory / f"{name}.sig").write_text(signature, encoding="utf-8")


def test_build_and_validate_multiplatform_manifest(tmp_path: Path) -> None:
    create_signed_asset(tmp_path, "PlotPilot_4.8.1_x64-setup.exe", "windows-signature")
    create_signed_asset(tmp_path, "PlotPilot_4.8.1_aarch64.app.tar.gz", "arm-signature")
    create_signed_asset(tmp_path, "PlotPilot_4.8.1_x64.app.tar.gz", "intel-signature")
    (tmp_path / "PlotPilot_4.8.1_aarch64.dmg").write_bytes(b"arm-dmg")
    (tmp_path / "PlotPilot_4.8.1_x64.dmg").write_bytes(b"intel-dmg")
    manifest = tmp_path / "latest.json"

    built = run_script(
        "build_updater_manifest.py",
        "--assets-dir",
        str(tmp_path),
        "--output",
        str(manifest),
        "--repository",
        "shenminglinyi/PlotPilot",
        "--tag",
        "v4.8.1",
        "--version",
        "4.8.1",
    )
    assert built.returncode == 0, built.stderr

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert set(data["platforms"]) == {
        "windows-x86_64",
        "windows-x86_64-nsis",
        "darwin-aarch64",
        "darwin-aarch64-app",
        "darwin-x86_64",
        "darwin-x86_64-app",
    }
    assert data["platforms"]["darwin-aarch64"]["url"].endswith(
        "/PlotPilot_4.8.1_aarch64.app.tar.gz"
    )

    validated = run_script(
        "validate_updater_manifest.py",
        "--manifest",
        str(manifest),
        "--assets-dir",
        str(tmp_path),
        "--repository",
        "shenminglinyi/PlotPilot",
        "--tag",
        "v4.8.1",
        "--version",
        "4.8.1",
    )
    assert validated.returncode == 0, validated.stderr


def test_validator_rejects_signature_mismatch(tmp_path: Path) -> None:
    create_signed_asset(tmp_path, "PlotPilot_4.8.1_x64-setup.exe", "windows-signature")
    create_signed_asset(tmp_path, "PlotPilot_4.8.1_aarch64.app.tar.gz", "arm-signature")
    create_signed_asset(tmp_path, "PlotPilot_4.8.1_x64.app.tar.gz", "intel-signature")
    (tmp_path / "PlotPilot_4.8.1_aarch64.dmg").write_bytes(b"arm-dmg")
    (tmp_path / "PlotPilot_4.8.1_x64.dmg").write_bytes(b"intel-dmg")
    manifest = tmp_path / "latest.json"
    assert run_script(
        "build_updater_manifest.py",
        "--assets-dir",
        str(tmp_path),
        "--output",
        str(manifest),
        "--repository",
        "shenminglinyi/PlotPilot",
        "--tag",
        "v4.8.1",
        "--version",
        "4.8.1",
    ).returncode == 0

    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["platforms"]["darwin-aarch64"]["signature"] = "tampered"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    validated = run_script(
        "validate_updater_manifest.py",
        "--manifest",
        str(manifest),
        "--assets-dir",
        str(tmp_path),
        "--repository",
        "shenminglinyi/PlotPilot",
        "--tag",
        "v4.8.1",
        "--version",
        "4.8.1",
    )
    assert validated.returncode != 0
    assert "does not match" in validated.stderr
