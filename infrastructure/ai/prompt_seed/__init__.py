"""提示词包（prompt_packages）种子加载 — CPMS 单一仓库入口。

仓库目录：``infrastructure/ai/prompt_packages/``
  - bundle_meta.yaml — 模板包元数据与种子版本号
  - nodes/<node_key>/ — package.yaml + system.md + user.md + 可选 extras.json

运行时由 PromptManager.ensure_seeded() 调用 load_seed_bundle()，不再读取 prompts_*.json。
"""
from __future__ import annotations

from infrastructure.ai.prompt_seed.loader import (
    PACKAGES_ROOT,
    load_seed_bundle,
    merge_legacy_json_prompts,
)
from infrastructure.ai.prompt_seed.normalize import normalize_prompt_record

__all__ = [
    "PACKAGES_ROOT",
    "load_seed_bundle",
    "merge_legacy_json_prompts",
    "normalize_prompt_record",
]
