"""从仓库根目录 `shared/taxonomy/` 加载通用题材 Bundle（JSON，与前端 @shared 同源）。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


def taxonomy_json_path(bundle_file: str = "builtin_cn_v1.json") -> Path:
    """`application/core/taxonomy/builtin_cn.py` 上溯 4 级到仓库根。"""
    here = Path(__file__).resolve()
    root = here.parents[3]
    return root / "shared" / "taxonomy" / bundle_file


def load_taxonomy_bundle_dict(bundle_file: str = "builtin_cn_v1.json") -> Dict[str, Any]:
    p = taxonomy_json_path(bundle_file)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def get_builtin_cn_bundle_cached(bundle_file: str = "builtin_cn_v1.json") -> Dict[str, Any]:
    return load_taxonomy_bundle_dict(bundle_file)
