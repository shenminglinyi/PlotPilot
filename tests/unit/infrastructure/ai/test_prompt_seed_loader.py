"""prompt_packages / prompt_seed 加载与规范化单测。"""
from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.ai.prompt_seed.loader import PACKAGES_ROOT, load_seed_bundle, load_node_dir
from infrastructure.ai.prompt_seed.normalize import normalize_prompt_record


def test_normalize_merges_underscore_fields_into_variables():
    raw = {
        "id": "test-node",
        "variables": [{"name": "x", "type": "string"}],
        "_directives": {"OPENING": "hello"},
    }
    n = normalize_prompt_record(raw)
    names = {v.get("name") for v in n["variables"]}
    assert "_directives" in names
    assert "x" in names


def test_load_seed_bundle_non_empty():
    meta, prompts = load_seed_bundle()
    assert meta.get("version")
    assert len(prompts) >= 1
    ids = {p.get("id") for p in prompts}
    assert "chapter-generation-main" in ids


def test_load_node_dir_roundtrip(tmp_path: Path):
    nd = tmp_path / "my-node"
    nd.mkdir()
    (nd / "package.yaml").write_text(
        "id: my-node\nname: T\ncategory: generation\ntags: []\nvariables: []\n",
        encoding="utf-8",
    )
    (nd / "system.md").write_text("SYS", encoding="utf-8")
    (nd / "user.md").write_text("USR", encoding="utf-8")
    rec = load_node_dir(nd)
    assert rec["system"] == "SYS"
    assert rec["user_template"] == "USR"
    norm = normalize_prompt_record(rec)
    assert norm["id"] == "my-node"


@pytest.mark.skipif(not (PACKAGES_ROOT / "nodes").is_dir(), reason="no prompt_packages")
def test_lifecycle_extras_present():
    ex = PACKAGES_ROOT / "nodes" / "lifecycle-phase-directives" / "extras.json"
    assert ex.is_file(), "lifecycle 节点应含 extras.json（_directives）"
