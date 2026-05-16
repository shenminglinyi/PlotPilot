"""从仓库根目录 `shared/taxonomy/*.yaml` 加载通用题材 Bundle（权威格式为 YAML）。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


def taxonomy_bundle_yaml_path(bundle_id: str) -> Path:
    """`application/core/taxonomy/builtin_cn.py` 上溯 4 级到仓库根。"""
    here = Path(__file__).resolve()
    root = here.parents[3]
    return root / "shared" / "taxonomy" / f"{bundle_id}.yaml"


def load_taxonomy_bundle_dict(bundle_id: str = "builtin_cn_v1") -> Dict[str, Any]:
    p = taxonomy_bundle_yaml_path(bundle_id)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return yaml.safe_load(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def get_builtin_cn_bundle_cached(bundle_id: str = "builtin_cn_v1") -> Dict[str, Any]:
    return load_taxonomy_bundle_dict(bundle_id)
