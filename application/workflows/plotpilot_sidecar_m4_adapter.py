from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

from domain.ai.value_objects.prompt import Prompt


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_ROOT = WORKSPACE_ROOT / "scripts"
if SCRIPTS_ROOT.is_dir():
    scripts_root = str(SCRIPTS_ROOT)
    if scripts_root not in sys.path:
        sys.path.insert(0, scripts_root)

try:
    from creative_sidecar.source_registry import load_writing_research_registry
except Exception:  # pragma: no cover - optional sidecar registry may be absent
    load_writing_research_registry = None  # type: ignore[assignment]


DEFAULT_SELECTABLE_STATUSES = {"active"}
DEFAULT_CAPABILITY_LIMIT = 2
DEFAULT_METHOD_LIMIT = 1
DEFAULT_FAILURE_LIMIT = 1


def classify_node_type(
    *,
    beat_prompt: str | None = None,
    beat_mode: bool = False,
    node_type: str | None = None,
) -> str:
    explicit_node_type = (node_type or "").strip()
    if explicit_node_type:
        return explicit_node_type
    if beat_mode or (beat_prompt or "").strip():
        return "beat_prose"
    return "chapter_prose"


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _normalize_research_asset(asset: dict[str, Any]) -> dict[str, Any] | None:
    asset_type = str(asset.get("asset_type") or "").strip()
    asset_id = (
        asset.get("asset_id")
        or asset.get("capability_id")
        or asset.get("method_id")
        or asset.get("failure_id")
        or ""
    )
    asset_id = str(asset_id).strip()
    if not asset_id:
        return None

    if asset_type == "capability":
        asset_type = "capability_card"
    elif asset_type == "method_card":
        asset_type = "method_card"
    elif asset_type == "failure_case":
        asset_type = "failure_case"
    else:
        asset_type = asset_type or "research_asset"

    return {
        "asset_type": asset_type,
        "asset_id": asset_id,
        "version": str(asset.get("version") or "0.1").strip() or "0.1",
        "status": str(asset.get("status") or "active").strip() or "active",
        "source": str(asset.get("source") or asset.get("source_file") or "").strip(),
        "source_anchor": str(asset.get("source_anchor") or "").strip(),
        "source_line": int(asset.get("source_line") or 0),
        "node_scope": _as_list(asset.get("node_scope") or asset.get("applicable_nodes")),
        "usage": str(asset.get("usage") or "").strip(),
    }


def _node_scope_score(node_type: str, node_scope: list[str]) -> int:
    scope = set(node_scope)
    if node_type == "beat_prose":
        priorities = ["beat_prose", "beat_scene", "chapter_prose", "next_chapter", "chapter_structure"]
    elif node_type == "chapter_prose":
        priorities = ["chapter_prose", "beat_prose", "beat_scene", "next_chapter", "chapter_structure"]
    elif node_type == "chapter_outline":
        priorities = ["chapter_outline", "chapter_structure", "next_chapter", "beat_scene", "beat_prose"]
    elif node_type == "outline_partition":
        priorities = ["outline_partition", "beat_scene", "chapter_structure", "chapter_outline", "next_chapter"]
    elif node_type in {"beat_sheet", "planning_beat_sheet"}:
        priorities = ["beat_sheet", "beat_scene", "chapter_structure", "chapter_outline", "next_chapter"]
    elif node_type == "main_plot":
        priorities = ["main_plot", "next_chapter", "chapter_structure", "beat_scene", "chapter_prose"]
    elif node_type == "dag_exec_writer":
        priorities = ["dag_exec_writer", "chapter_prose", "beat_prose", "next_chapter", "beat_scene"]
    elif node_type in {"planning_quick_macro", "planning_act"}:
        priorities = [node_type, "main_plot", "chapter_structure", "next_chapter", "beat_scene"]
    else:
        priorities = ["chapter_prose", "beat_prose", "beat_scene", "next_chapter", "chapter_structure"]

    for score, candidate in enumerate(priorities, start=1):
        if candidate in scope:
            return len(priorities) - score + 1
    return 0


def _sort_assets(node_type: str, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(asset: dict[str, Any]) -> tuple[int, str]:
        return (
            _node_scope_score(node_type, list(asset.get("node_scope") or [])),
            str(asset.get("asset_id") or ""),
        )

    return sorted(assets, key=sort_key, reverse=True)


def _default_registry() -> dict[str, Any]:
    if load_writing_research_registry is None:
        return {"research_assets": []}
    return load_writing_research_registry()


def select_research_assets(
    registry: dict[str, Any] | None = None,
    *,
    node_type: str,
    max_capability_cards: int = DEFAULT_CAPABILITY_LIMIT,
    max_method_cards: int = DEFAULT_METHOD_LIMIT,
    max_failure_cases: int = DEFAULT_FAILURE_LIMIT,
) -> list[dict[str, Any]]:
    source_registry = registry or _default_registry()
    raw_assets = source_registry.get("research_assets") or []
    normalized: list[dict[str, Any]] = []
    for item in raw_assets:
        if not isinstance(item, dict):
            continue
        asset = _normalize_research_asset(item)
        if asset is None:
            continue
        if asset["asset_type"] not in {"capability_card", "method_card", "failure_case"}:
            continue
        if asset["status"] not in DEFAULT_SELECTABLE_STATUSES:
            continue
        if not asset["node_scope"]:
            continue
        normalized.append(asset)

    capability_cards = [asset for asset in normalized if asset["asset_type"] == "capability_card"]
    method_cards = [asset for asset in normalized if asset["asset_type"] == "method_card"]
    failure_cases = [asset for asset in normalized if asset["asset_type"] == "failure_case"]

    selected = _sort_assets(node_type, capability_cards)[:max_capability_cards]
    selected.extend(_sort_assets(node_type, method_cards)[:max_method_cards])
    selected.extend(_sort_assets(node_type, failure_cases)[:max_failure_cases])
    return selected


def _render_sidecar_block(
    *,
    node_type: str,
    native_call_boundary: dict[str, Any],
    selected_assets: list[dict[str, Any]],
) -> str:
    asset_lines = []
    for asset in selected_assets:
        scope = ", ".join(asset.get("node_scope") or [])
        asset_lines.append(
            "- asset_type: {asset_type} | asset_id: {asset_id} | version: {version} | status: {status} | source: {source} | node_scope: {scope}".format(
                asset_type=asset["asset_type"],
                asset_id=asset["asset_id"],
                version=asset["version"],
                status=asset["status"],
                source=asset["source"],
                scope=scope,
            )
        )

    boundary = native_call_boundary.get("source_function") or "AutoNovelGenerationWorkflow._build_prompt"
    return "\n".join(
        [
            "【Sidecar M4 pre-generation】",
            "enhancement_mode: pre_generation",
            f"node_type: {node_type}",
            f"native_call_boundary: {boundary}",
            "selected research assets:",
            *asset_lines,
            "rules:",
            "- Keep the original PlotPilot prompt intact.",
            "- Use only the selected research assets for this native call.",
            "- Do not add a post-generation rewrite.",
        ]
    )


def enhance_prompt_for_plotpilot_m4(
    prompt: Prompt,
    *,
    beat_prompt: str | None = None,
    beat_mode: bool = False,
    node_type: str | None = None,
    native_call_boundary: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    fail_closed: bool = False,
) -> tuple[Prompt, dict[str, Any]]:
    node_type = classify_node_type(beat_prompt=beat_prompt, beat_mode=beat_mode, node_type=node_type)
    boundary = native_call_boundary or {
        "source_file": "systems/PlotPilot/application/workflows/auto_novel_generation_workflow.py",
        "source_function": "AutoNovelGenerationWorkflow._build_prompt",
    }
    trace: dict[str, Any] = {
        "enhancement_mode": "pre_generation",
        "node_type": node_type,
        "selector_policy_id": f"PLOTPILOT-M4-{node_type.upper()}-DEFAULT-0001",
        "selectable_statuses": sorted(DEFAULT_SELECTABLE_STATUSES),
        "native_call_boundary": boundary,
        "selected_assets": [],
        "injected_blocks": [],
        "sidecar_added_regeneration_count": 0,
        "enhancement_applied": False,
        "all_assets_resolved": False,
        "runtime_pack_matches_selection": False,
        "no_post_generation_rewrite": True,
        "active_registry_writeback": False,
    }

    try:
        selected_assets = select_research_assets(registry, node_type=node_type)
        if not selected_assets:
            raise ValueError("NO_SELECTABLE_RESEARCH_ASSETS")

        block = _render_sidecar_block(
            node_type=node_type,
            native_call_boundary=boundary,
            selected_assets=selected_assets,
        )
        enhanced_prompt = Prompt(system=prompt.system.rstrip() + "\n\n" + block, user=prompt.user)
        trace["selected_assets"] = selected_assets
        selected_asset_ids = [asset["asset_id"] for asset in selected_assets]
        trace["selected_asset_ids"] = selected_asset_ids
        trace["source_trace"] = {
            "native_call_boundary": boundary,
            "selected_asset_ids": selected_asset_ids,
            "asset_versions": {
                asset["asset_id"]: asset["version"]
                for asset in selected_assets
            },
            "asset_sources": {
                asset["asset_id"]: {
                    "source": asset.get("source") or "",
                    "source_anchor": asset.get("source_anchor") or "",
                    "source_line": asset.get("source_line") or 0,
                }
                for asset in selected_assets
            },
        }
        trace["injected_blocks"] = [
            {
                "block_id": "sidecar-m4-pre-generation",
                "target": "system",
                "position": "append",
                "asset_ids": [asset["asset_id"] for asset in selected_assets],
                "asset_count": len(selected_assets),
                "token_estimate": max(120, 60 * len(selected_assets)),
                "prompt_excerpt_hash": sha256(block.encode("utf-8")).hexdigest(),
            }
        ]
        trace["enhancement_applied"] = True
        trace["all_assets_resolved"] = True
        trace["runtime_pack_matches_selection"] = True
        return enhanced_prompt, trace
    except Exception as exc:
        trace["failure_reason"] = f"{type(exc).__name__}: {exc}"
        if fail_closed:
            raise
        return prompt, trace
