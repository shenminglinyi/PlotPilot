"""Finite declarative packages from a fixed repository-owned directory only."""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field
from application.plugin_pilot.contracts import HOST_API, StrictModel

OFFICIAL_ROOT = Path(__file__).resolve().parents[2] / "official-plugins"
ACTIONS = ("read_snapshot", "render_template", "invoke_model", "validate_artifact", "submit_artifact")


class Manifest(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=r"^0\.\d+\.\d+$")
    host_api: str
    artifact_type: str
    template: str
    steps: list[str]


@dataclass(frozen=True)
class Package:
    manifest: Manifest
    template: str
    digest: str


def _load_directory(root: Path) -> dict[str, Package]:
    """Internal test seam; production entry point never accepts a path."""
    packages = {}
    resolved_root = root.resolve()
    manifests = sorted(root.glob("*/manifest.json"))
    if len(manifests) > 10:
        raise ValueError("Too many official packages")
    for path in manifests:
        if not path.resolve().is_relative_to(resolved_root) or path.is_symlink():
            raise ValueError("Manifest escapes official directory")
        if path.stat().st_size > 8192:
            raise ValueError("Manifest too large")
        raw = path.read_bytes()
        manifest = Manifest.model_validate_json(raw)
        if manifest.host_api != HOST_API or manifest.artifact_type != "character_card_patch@1":
            raise ValueError("Incompatible host API or artifact type")
        if tuple(manifest.steps) != ACTIONS:
            raise ValueError("Unsupported action or action sequence")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.txt", manifest.template):
            raise ValueError("Only a local plain-text template is permitted")
        template_path = path.parent / manifest.template
        if (template_path.is_symlink() or not template_path.resolve().is_relative_to(path.parent.resolve())
                or not template_path.resolve().is_relative_to(resolved_root)):
            raise ValueError("Template escapes package directory")
        if template_path.stat().st_size > 6000:
            raise ValueError("Template too large")
        template = template_path.read_text(encoding="utf-8")
        if template.count("{{snapshot}}") != 1:
            raise ValueError("Template requires exactly one snapshot slot")
        if "{{" in template.replace("{{snapshot}}", ""):
            raise ValueError("Unknown template expression")
        if manifest.id in packages:
            raise ValueError("Duplicate plugin ID")
        packages[manifest.id] = Package(manifest, template,
                                        hashlib.sha256(raw + template.encode()).hexdigest())
    return packages


def load_official() -> dict[str, Package]:
    return _load_directory(OFFICIAL_ROOT)
