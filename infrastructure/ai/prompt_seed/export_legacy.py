"""一次性：从旧版 prompts_defaults.json + prompts_*.json 导出到 prompt_packages/。

用法（仓库根目录）::

    python -m infrastructure.ai.prompt_seed.export_legacy

导出后由 PromptManager 从 prompt_packages 加载种子；旧 JSON 可删除或归档。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from infrastructure.ai.prompt_seed.loader import PACKAGES_ROOT, merge_legacy_json_prompts


def _dump_package_yaml(meta: Dict[str, Any], dest: Path) -> None:
    import yaml  # type: ignore

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            meta,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )


def export_one(idx: int, record: Dict[str, Any], dest_root: Path) -> None:
    node_id = record.get("id", f"node-{idx}")
    node_dir = dest_root / node_id
    node_dir.mkdir(parents=True, exist_ok=True)

    system = record.get("system") or ""
    user = record.get("user_template") or ""

    extras = {k: v for k, v in record.items() if k.startswith("_") and k != "_meta"}
    body_keys = {
        "system",
        "user_template",
        "id",
    }
    package_meta: Dict[str, Any] = {}
    for k, v in record.items():
        if k in body_keys:
            continue
        if k.startswith("_"):
            continue
        package_meta[k] = v

    package_meta["id"] = node_id
    package_meta["sort_order"] = idx

    _dump_package_yaml(package_meta, node_dir / "package.yaml")
    (node_dir / "system.md").write_text(system, encoding="utf-8")
    (node_dir / "user.md").write_text(user, encoding="utf-8")

    if extras:
        (node_dir / "extras.json").write_text(
            json.dumps(extras, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        extra_path = node_dir / "extras.json"
        if extra_path.is_file():
            extra_path.unlink()


def export_all(
    *,
    prompts_dir: Path | None = None,
    dest_root: Path | None = None,
    bump_version: str | None = "4.0.0-prompt-packages",
) -> List[str]:
    merged_meta, prompts = merge_legacy_json_prompts(prompts_dir)
    root = dest_root or PACKAGES_ROOT
    nodes_root = root / "nodes"
    nodes_root.mkdir(parents=True, exist_ok=True)

    # 清空旧节点（保留 fragments 等）
    for child in list(nodes_root.iterdir()):
        if child.is_dir():
            import shutil

            shutil.rmtree(child)

    for idx, p in enumerate(prompts):
        export_one(idx, p, nodes_root)

    bundle = {
        "version": bump_version or merged_meta.get("version", "4.0.0"),
        "name": merged_meta.get("name", "PlotPilot 内置"),
        "description": merged_meta.get(
            "description",
            "CPMS 内置提示词（prompt_packages 目录化种子）",
        ),
        "author": merged_meta.get("author", "PlotPilot Team"),
        "engine": merged_meta.get("engine", "jinja2"),
        "changelog": "v4: 种子迁移为 prompt_packages（YAML 元数据 + Markdown 正文 + extras.json）",
    }
    _dump_package_yaml(bundle, root / "bundle_meta.yaml")

    (root / "fragments").mkdir(exist_ok=True)
    readme = root / "fragments" / "README.md"
    if not readme.is_file():
        readme.write_text(
            "# Fragments\n\n可放置可复用片段；构建管线可用 Jinja `include` 组装（后续扩展）。\n",
            encoding="utf-8",
        )

    return [str(p.get("id", "")) for p in prompts]


def main() -> None:
    parser = argparse.ArgumentParser(description="导出旧 JSON 种子为 prompt_packages")
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=None,
        help="默认 infrastructure/ai/prompts",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="默认 infrastructure/ai/prompt_packages",
    )
    parser.add_argument("--version", type=str, default="4.0.0-prompt-packages")
    args = parser.parse_args()

    ids = export_all(
        prompts_dir=args.prompts_dir,
        dest_root=args.dest,
        bump_version=args.version,
    )
    print(f"Exported {len(ids)} nodes to {(args.dest or PACKAGES_ROOT) / 'nodes'}")


if __name__ == "__main__":
    main()
