"""从 prompt_packages 目录加载与旧版 JSON 合并逻辑。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_AI_DIR = Path(__file__).resolve().parent.parent
PACKAGES_ROOT = _AI_DIR / "prompt_packages"
NODES_DIR = PACKAGES_ROOT / "nodes"
BUNDLE_META_FILE = PACKAGES_ROOT / "bundle_meta.yaml"
_LEGACY_PROMPTS_DIR = _AI_DIR / "prompts"
_LEGACY_GLOB = "prompts_*.json"


def _try_yaml_load(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError("需要安装 PyYAML：pip install PyYAML") from e
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def load_bundle_meta() -> Dict[str, Any]:
    """读取 bundle_meta.yaml；缺失时返回占位。"""
    if not BUNDLE_META_FILE.is_file():
        return {
            "version": "0.0.0",
            "name": "PlotPilot 内置",
            "description": "prompt_packages 缺失 bundle_meta.yaml",
            "author": "PlotPilot Team",
            "engine": "jinja2",
        }
    return _try_yaml_load(BUNDLE_META_FILE)


def load_node_dir(node_dir: Path) -> Dict[str, Any]:
    """加载单个节点目录为与旧种子一致的 dict（含 system / user_template）。"""
    pkg_path = node_dir / "package.yaml"
    if not pkg_path.is_file():
        raise FileNotFoundError(f"缺少 package.yaml: {node_dir}")

    meta = _try_yaml_load(pkg_path)
    node_id = meta.get("id") or node_dir.name

    system_path = node_dir / "system.md"
    user_path = node_dir / "user.md"
    system = system_path.read_text(encoding="utf-8") if system_path.is_file() else ""
    user = user_path.read_text(encoding="utf-8") if user_path.is_file() else ""

    extras_path = node_dir / "extras.json"
    extras: Dict[str, Any] = {}
    if extras_path.is_file():
        extras = json.loads(extras_path.read_text(encoding="utf-8"))
        if not isinstance(extras, dict):
            extras = {}

    record: Dict[str, Any] = {**meta, "id": node_id, "system": system, "user_template": user}
    for k, v in extras.items():
        if k not in record or k.startswith("_"):
            record[k] = v

    return record


def load_seed_bundle() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """返回 (合并后的 _meta, prompts 列表)。无节点目录时 prompts 为空。"""
    bundle_meta = load_bundle_meta()
    if not NODES_DIR.is_dir():
        logger.warning("prompt_packages/nodes 不存在，种子列表为空")
        return bundle_meta, []

    rows: List[Dict[str, Any]] = []
    for child in sorted(NODES_DIR.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        try:
            rows.append(load_node_dir(child))
        except Exception as exc:
            logger.error("加载提示词包失败 %s: %s", child, exc)
            raise

    rows.sort(key=lambda r: (r.get("sort_order", 10_000), r.get("id", "")))
    return bundle_meta, rows


def merge_legacy_json_prompts(prompts_dir: Path | None = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """与旧 PromptManager 相同合并规则：defaults 全量 _meta，再 prompts_*.json 覆盖同名 id 并刷新 version。"""
    base = prompts_dir or _LEGACY_PROMPTS_DIR
    all_prompts: Dict[str, Dict[str, Any]] = {}
    merged_meta: Dict[str, Any] = {}

    default_path = base / "prompts_defaults.json"
    if default_path.is_file():
        data = json.loads(default_path.read_text(encoding="utf-8"))
        merged_meta.update(data.get("_meta") or {})
        for p in data.get("prompts", []):
            if p.get("id"):
                all_prompts[p["id"]] = p

    if base.is_dir():
        for cat_file in sorted(base.glob(_LEGACY_GLOB)):
            data = json.loads(cat_file.read_text(encoding="utf-8"))
            cat_meta = data.get("_meta", {})
            if cat_meta.get("version"):
                merged_meta["version"] = cat_meta["version"]
            for p in data.get("prompts", []):
                if p.get("id"):
                    all_prompts[p["id"]] = p

    # 与 dict 插入顺序一致（Py3.7+）：先 defaults 顺序，后逐文件覆盖且不改变已有 key 顺序
    return merged_meta, list(all_prompts.values())
